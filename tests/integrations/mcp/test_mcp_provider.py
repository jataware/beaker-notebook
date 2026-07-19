"""Tests for the MCPIntegrationProvider and its helpers.

Covers the pure helpers, config parsing, config-file discovery, the kept-open
connection lifecycle (the ``_ServerConnection`` actor), catalog population,
prompt rendering, and the generic dispatch ``@tool`` methods. Live MCP servers
are never contacted: sessions are replaced with in-memory fakes, and the actor
is exercised against a faked transport + ``ClientSession``.
"""

import asyncio
import io
import json
import textwrap
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from beaker_notebook.lib.integrations.mcp import (
    MCPIntegration,
    MCPIntegrationProvider,
    MCPPromptResource,
    MCPResourceResource,
    MCPServerConfig,
    MCPToolResource,
    _ServerConnection,
    _json_schema_type,
)


# ---------------------------------------------------------------------------
# In-memory fakes standing in for MCP wire types / sessions
# ---------------------------------------------------------------------------


def _tool(name, description=None, input_schema=None):
    return SimpleNamespace(name=name, description=description, inputSchema=input_schema)


def _resource(uri, name, description=None, mime_type=None):
    return SimpleNamespace(uri=uri, name=name, description=description, mimeType=mime_type)


def _prompt(name, description=None, arguments=None):
    return SimpleNamespace(name=name, description=description, arguments=arguments)


def _prompt_arg(name, description=None, required=False):
    return SimpleNamespace(name=name, description=description, required=required)


def _make_init_result(*, serverInfo=None, instructions=None):
    """Build a real ``InitializeResult`` for tests that assert identity mapping."""
    from mcp.types import Implementation, InitializeResult, ServerCapabilities

    info_kwargs = {"name": "srv", "version": "1.2.3"}
    info_kwargs.update(serverInfo or {})
    return InitializeResult(
        protocolVersion="2025-06-18",
        capabilities=ServerCapabilities(),
        serverInfo=Implementation(**info_kwargs),
        instructions=instructions,
    )


class _Unsupported:
    """Sentinel: a primitive family the server does not implement."""


class FakeSession:
    """Minimal stand-in for ``mcp.ClientSession``.

    Each ``list_*`` family may be set to ``_Unsupported`` to simulate a server
    that raises on that request (mirrors real servers implementing only a
    subset of primitives).
    """

    def __init__(
        self,
        *,
        tools=None,
        resources=None,
        prompts=None,
        call_result=None,
        read_result=None,
        init_result=None,
        init_error=None,
    ):
        self._tools = tools
        self._resources = resources
        self._prompts = prompts
        self._call_result = call_result
        self._read_result = read_result
        self._init_result = init_result
        self._init_error = init_error
        self.calls: list[tuple] = []

    async def initialize(self):
        if self._init_error is not None:
            raise self._init_error
        return self._init_result if self._init_result is not None else _make_init_result()

    async def list_tools(self):
        if self._tools is _Unsupported:
            raise RuntimeError("tools/list not supported")
        return SimpleNamespace(tools=self._tools or [])

    async def list_resources(self):
        if self._resources is _Unsupported:
            raise RuntimeError("resources/list not supported")
        return SimpleNamespace(resources=self._resources or [])

    async def list_prompts(self):
        if self._prompts is _Unsupported:
            raise RuntimeError("prompts/list not supported")
        return SimpleNamespace(prompts=self._prompts or [])

    async def call_tool(self, name, arguments):
        self.calls.append(("call_tool", name, arguments))
        return self._call_result

    async def read_resource(self, uri):
        self.calls.append(("read_resource", str(uri)))
        return self._read_result


class FakeConnection:
    """Stand-in for ``_ServerConnection`` that runs ops inline against a session.

    Used by the dispatch/catalog tests, which care only that an op is executed
    against the session and its result flattened -- not about the owner-task
    machinery (that is covered by ``TestConnectionLifecycle`` against the real
    actor).
    """

    def __init__(self, session=None, *, init_result=None):
        self._session = session
        self.init_result = init_result if init_result is not None else _make_init_result()
        self.running = True
        self.closed = False

    async def run(self, op):
        return await op(self._session)

    async def close(self):
        self.closed = True
        self.running = False


def _install_fake_connection(provider, session, *, slug="filesystem", init_result=None):
    """Register a fake kept-open connection and stub ``_ensure_connected``.

    The connection is placed in ``provider._connections`` (so ``_populate_*``
    find it) and returned from ``_ensure_connected``; yields the connection.
    """
    integ = provider._find_server_by_slug(slug)
    conn = FakeConnection(session, init_result=init_result)
    provider._connections[integ.uuid] = conn
    return patch.object(provider, "_ensure_connected", new=AsyncMock(return_value=conn))


@contextmanager
def _fake_transport_and_session(provider, session):
    """Run the real actor without a live server: fake transport + ClientSession.

    ``_open_transport`` returns a ``(transport, logfile)`` pair (matching the
    real signature): the transport yields dummy streams, and the patched
    ``ClientSession`` hands back ``session`` (whose ``initialize()`` returns an
    InitializeResult), so ``_ServerConnection`` runs end-to-end in-memory on
    the event loop.
    """

    class _FakeTransport:
        async def __aenter__(self):
            return (SimpleNamespace(), SimpleNamespace())

        async def __aexit__(self, *exc):
            return False

    class _FakeClientSession:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    with patch.object(
        provider, "_open_transport", side_effect=lambda config: (_FakeTransport(), io.BytesIO())
    ), patch(
        "beaker_notebook.lib.integrations.mcp.ClientSession",
        lambda *a, **k: _FakeClientSession(),
    ):
        yield


# ---------------------------------------------------------------------------
# Provider construction helpers
# ---------------------------------------------------------------------------


def _make_provider(config_paths=None, search_roots=None) -> MCPIntegrationProvider:
    """Construct a provider without contacting any server.

    Discovery only parses config; no connections are opened at construction
    time, so nothing needs stubbing beyond the config search roots.
    """
    with patch(
        "beaker_notebook.lib.integrations.mcp.find_resource_dirs", return_value=[],
    ), patch.object(
        MCPIntegrationProvider, "_get_config_search_roots", return_value=list(search_roots or []),
    ):
        return MCPIntegrationProvider(config_paths=config_paths)


def _agent_ref(session_id: str = "kernel-1"):
    return SimpleNamespace(
        context=SimpleNamespace(subkernel=SimpleNamespace(kernel_id=session_id))
    )


# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------

MCP_JSON = {
    "mcpServers": {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "env": {"LOG_LEVEL": "info"},
        },
        "deepwiki": {
            "type": "http",
            "url": "https://mcp.deepwiki.com/mcp",
        },
    }
}

MCP_YAML = textwrap.dedent("""\
    servers:
      filesystem:
        title: Filesystem tools
        transport: stdio
        command: npx
        args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/matt"]
        description: Read and write files.
      remote:
        type: http
        url: https://example.com/mcp
        disabled: true
""")


@pytest.fixture
def json_config(tmp_path: Path) -> Path:
    p = tmp_path / "mcp.json"
    p.write_text(json.dumps(MCP_JSON))
    return p


@pytest.fixture
def yaml_config(tmp_path: Path) -> Path:
    p = tmp_path / "mcp.yaml"
    p.write_text(MCP_YAML)
    return p


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestJsonSchemaType:
    def test_plain_type(self):
        assert _json_schema_type({"type": "string"}) == "string"

    def test_list_type(self):
        assert _json_schema_type({"type": ["string", "null"]}) == "string|null"

    def test_anyof(self):
        spec = {"anyOf": [{"type": "string"}, {"type": "number"}]}
        assert _json_schema_type(spec) == "string|number"

    def test_oneof(self):
        spec = {"oneOf": [{"type": "boolean"}, {"type": "integer"}]}
        assert _json_schema_type(spec) == "boolean|integer"

    def test_enum(self):
        assert _json_schema_type({"enum": ["a", "b"]}) == "enum"

    def test_fallback_any(self):
        assert _json_schema_type({}) == "any"


class TestFlattenContent:
    def test_text_blocks_joined(self):
        blocks = [SimpleNamespace(text="hello"), SimpleNamespace(text="world")]
        assert MCPIntegrationProvider._flatten_content(blocks) == "hello\nworld"

    def test_non_text_block_placeholder(self):
        blocks = [SimpleNamespace(text="a"), SimpleNamespace(type="image", text=None)]
        out = MCPIntegrationProvider._flatten_content(blocks)
        assert "a" in out
        assert "<non-text content block: image>" in out

    def test_empty(self):
        assert MCPIntegrationProvider._flatten_content(None) == ""


class TestFlattenResourceContents:
    def test_text_items(self):
        items = [SimpleNamespace(text="one"), SimpleNamespace(text="two")]
        assert MCPIntegrationProvider._flatten_resource_contents(items) == "one\ntwo"

    def test_blob_item_placeholder(self):
        items = [SimpleNamespace(blob="QUJD", mimeType="image/png")]
        out = MCPIntegrationProvider._flatten_resource_contents(items)
        assert "binary resource" in out
        assert "image/png" in out

    def test_empty(self):
        assert MCPIntegrationProvider._flatten_resource_contents(None) == ""


class TestSchemaArgumentsToDict:
    def test_none_when_no_properties(self):
        assert MCPIntegrationProvider._schema_arguments_to_dict({}) is None
        assert MCPIntegrationProvider._schema_arguments_to_dict({"properties": {}}) is None

    def test_required_and_types(self):
        schema = {
            "properties": {
                "path": {"type": "string", "description": "a path"},
                "count": {"type": "integer"},
            },
            "required": ["path"],
        }
        args = MCPIntegrationProvider._schema_arguments_to_dict(schema)
        by_name = {a["name"]: a for a in args}
        assert by_name["path"]["required"] is True
        assert by_name["path"]["type"] == "string"
        assert by_name["path"]["description"] == "a path"
        assert by_name["count"]["required"] is False
        assert "description" not in by_name["count"]


# ---------------------------------------------------------------------------
# MCPServerConfig
# ---------------------------------------------------------------------------


class TestMCPServerConfig:
    def test_from_dict_stdio(self):
        cfg = MCPServerConfig.from_dict(
            "fs", {"command": "npx", "args": ["-y", "x"], "env": {"A": "1"}}
        )
        assert cfg.name == "fs"
        assert cfg.command == "npx"
        assert cfg.args == ["-y", "x"]
        assert cfg.env == {"A": "1"}
        assert cfg.resolved_transport == "stdio"
        # Title is left unset when not explicitly configured; the integration
        # display name then falls back to the slug.
        assert cfg.title is None

    def test_from_dict_http_via_type(self):
        cfg = MCPServerConfig.from_dict("api", {"type": "http", "url": "https://x/mcp"})
        assert cfg.url == "https://x/mcp"
        assert cfg.resolved_transport == "http"

    def test_from_dict_transport_key(self):
        cfg = MCPServerConfig.from_dict(
            "s", {"transport": "sse", "url": "https://x/sse"}
        )
        assert cfg.resolved_transport == "sse"

    def test_from_dict_disabled(self):
        cfg = MCPServerConfig.from_dict("s", {"command": "x", "disabled": True})
        assert cfg.disabled is True

    def test_from_dict_metadata_title_and_description(self):
        cfg = MCPServerConfig.from_dict(
            "s",
            {
                "command": "x",
                "x-beaker-notebook": {"title": "Nice Title", "description": "desc"},
            },
        )
        assert cfg.title == "Nice Title"
        assert cfg.description == "desc"
        assert cfg.metadata == {"title": "Nice Title", "description": "desc"}

    def test_top_level_title_wins_over_metadata(self):
        cfg = MCPServerConfig.from_dict(
            "s",
            {"command": "x", "title": "Top", "x-beaker-notebook": {"title": "Meta"}},
        )
        assert cfg.title == "Top"

    def test_resolved_transport_infers_stdio_from_command(self):
        assert MCPServerConfig(name="s", command="x").resolved_transport == "stdio"

    def test_resolved_transport_infers_http_from_url(self):
        assert MCPServerConfig(name="s", url="https://x").resolved_transport == "http"

    def test_resolved_transport_explicit_override(self):
        # Even with a command present, an explicit transport wins.
        cfg = MCPServerConfig(name="s", command="x", transport="sse", url="https://x")
        assert cfg.resolved_transport == "sse"

    def test_resolved_transport_raises_without_command_or_url(self):
        with pytest.raises(ValueError, match="neither command nor url"):
            _ = MCPServerConfig(name="s").resolved_transport


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_discover_from_json(self, json_config: Path):
        integrations = MCPIntegrationProvider.discover_integrations(paths=[json_config])
        slugs = {i.slug for i in integrations.values()}
        assert slugs == {"filesystem", "deepwiki"}

    def test_discover_from_yaml(self, yaml_config: Path):
        integrations = MCPIntegrationProvider.discover_integrations(paths=[yaml_config])
        slugs = {i.slug for i in integrations.values()}
        # 'remote' is disabled and must be skipped.
        assert slugs == {"filesystem"}

    def test_discover_from_yml_extension(self, tmp_path: Path):
        # The .yml extension is searched for in the default globs, so it must
        # parse as YAML rather than being rejected as an unknown extension.
        p = tmp_path / "mcp.yml"
        p.write_text(MCP_YAML)
        integrations = MCPIntegrationProvider.discover_integrations(paths=[p])
        assert {i.slug for i in integrations.values()} == {"filesystem"}

    def test_dotmcp_yml_extension(self, tmp_path: Path):
        p = tmp_path / ".mcp.yml"
        p.write_text(MCP_YAML)
        integrations = MCPIntegrationProvider.discover_integrations(paths=[p])
        assert {i.slug for i in integrations.values()} == {"filesystem"}

    def test_unknown_extension_skipped(self, tmp_path: Path):
        bad = tmp_path / "mcp.txt"
        bad.write_text("servers:\n  fs:\n    command: x\n")
        good = tmp_path / "mcp.json"
        good.write_text(json.dumps({"mcpServers": {"fs": {"command": "x"}}}))
        integrations = MCPIntegrationProvider.discover_integrations(paths=[bad, good])
        assert {i.slug for i in integrations.values()} == {"fs"}

    def test_disabled_server_skipped(self, yaml_config: Path):
        integrations = MCPIntegrationProvider.discover_integrations(paths=[yaml_config])
        assert all(i.slug != "remote" for i in integrations.values())

    def test_transport_detected(self, json_config: Path):
        integrations = MCPIntegrationProvider.discover_integrations(paths=[json_config])
        by_slug = {i.slug: i for i in integrations.values()}
        assert by_slug["filesystem"].server_config.resolved_transport == "stdio"
        assert by_slug["deepwiki"].server_config.resolved_transport == "http"

    def test_duplicate_name_across_files_loaded_once(self, tmp_path: Path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        a.write_text(json.dumps({"mcpServers": {"fs": {"command": "x"}}}))
        b.write_text(json.dumps({"mcpServers": {"fs": {"command": "y"}}}))
        integrations = MCPIntegrationProvider.discover_integrations(paths=[a, b])
        fs = [i for i in integrations.values() if i.slug == "fs"]
        assert len(fs) == 1
        # First file wins.
        assert fs[0].server_config.command == "x"

    def test_missing_mapping_ignored(self, tmp_path: Path):
        p = tmp_path / "mcp.json"
        p.write_text(json.dumps({"something_else": {}}))
        integrations = MCPIntegrationProvider.discover_integrations(paths=[p])
        assert integrations == {}

    def test_unreadable_file_skipped(self, tmp_path: Path):
        bad = tmp_path / "mcp.json"
        bad.write_text("{ not valid json")
        good = tmp_path / "good.json"
        good.write_text(json.dumps({"mcpServers": {"fs": {"command": "x"}}}))
        integrations = MCPIntegrationProvider.discover_integrations(paths=[bad, good])
        assert {i.slug for i in integrations.values()} == {"fs"}

    def test_nonexistent_path_ignored(self, tmp_path: Path):
        integrations = MCPIntegrationProvider.discover_integrations(
            paths=[tmp_path / "nope.json"]
        )
        assert integrations == {}

    def test_build_integration_fields(self):
        cfg = MCPServerConfig.from_dict("fs", {"command": "npx"})
        integ = MCPIntegrationProvider._build_integration(cfg)
        assert isinstance(integ, MCPIntegration)
        assert integ.slug == "fs"
        assert integ.datatype == "mcp"
        assert integ.provider == "mcp:mcp"
        assert integ.server_config is cfg
        # No configured title: name falls back to the slug, server_title unset.
        assert integ.name == "fs"
        assert integ.server_title is None

    def test_build_integration_name_from_title(self):
        # A configured title becomes both the display name and server_title,
        # while the slug remains the config key.
        cfg = MCPServerConfig.from_dict("fs", {"command": "npx", "title": "File System"})
        integ = MCPIntegrationProvider._build_integration(cfg)
        assert integ.slug == "fs"
        assert integ.name == "File System"
        assert integ.server_title == "File System"

    def test_build_integration_records_corpus(self):
        # Context-provided servers are namespaced under a corpus, which drives
        # the read-only vs editable distinction in the UI.
        cfg = MCPServerConfig.from_dict("fs", {"command": "npx"})
        integ = MCPIntegrationProvider._build_integration(cfg, corpus="context-foo")
        assert integ.corpus == "context-foo"


# ---------------------------------------------------------------------------
# _get_config_search_roots
# ---------------------------------------------------------------------------


class TestConfigSearchRoots:
    def test_returns_existing_only(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".beaker").mkdir()
        with patch(
            "beaker_notebook.lib.integrations.mcp.find_resource_dirs", return_value=[],
        ), patch.object(Path, "home", return_value=tmp_path / "_nohome"):
            roots = MCPIntegrationProvider._get_config_search_roots()
        root_strs = [str(r) for r in roots]
        assert str(tmp_path / ".beaker") in root_strs
        assert str(tmp_path / ".agents") not in root_strs


class TestOpenTransport:
    """Every transport must return the (transport_cm, logfile) pair that
    _ServerConnection._run unpacks; a bare context manager would crash on
    connect (regression guard for the sse branch)."""

    @pytest.mark.parametrize(
        "config",
        [
            MCPServerConfig(name="s", command="echo", transport="stdio"),
            MCPServerConfig(name="h", url="https://example.com/mcp", transport="http"),
            MCPServerConfig(name="e", url="https://example.com/sse", transport="sse"),
        ],
        ids=["stdio", "http", "sse"],
    )
    def test_returns_transport_logfile_pair(self, config):
        provider = _make_provider()
        transport, logfile = provider._open_transport(config)
        assert hasattr(transport, "__aenter__")
        # logfile must be a readable buffer the failure handler can drain.
        logfile.seek(0)
        assert isinstance(logfile.read(), bytes)


# ---------------------------------------------------------------------------
# Catalog population
# ---------------------------------------------------------------------------


class TestCatalogPopulation:
    @pytest.fixture
    def provider(self, json_config: Path) -> MCPIntegrationProvider:
        return _make_provider(config_paths=[json_config])

    def _integration(self, provider) -> MCPIntegration:
        return provider._find_server_by_slug("filesystem")

    async def test_loads_tools_resources_prompts(self, provider):
        integ = self._integration(provider)
        session = FakeSession(
            tools=[_tool("read_file", "reads", {"type": "object"})],
            resources=[_resource("file:///a", "a", "res a", "text/plain")],
            prompts=[
                _prompt("summarize", "sum", [_prompt_arg("topic", "the topic", True)])
            ],
        )
        provider._connections[integ.uuid] = FakeConnection(session)
        await provider._populate_resources(integ)

        tools = [r for r in integ.resources.values() if isinstance(r, MCPToolResource)]
        resources = [r for r in integ.resources.values() if isinstance(r, MCPResourceResource)]
        prompts = [r for r in integ.resources.values() if isinstance(r, MCPPromptResource)]

        assert integ.resources_loaded is True
        assert len(tools) == 1 and tools[0].tool_name == "read_file"
        assert tools[0].input_schema == {"type": "object"}
        assert len(resources) == 1 and resources[0].uri == "file:///a"
        assert resources[0].mime_type == "text/plain"
        assert len(prompts) == 1 and prompts[0].prompt_name == "summarize"
        assert prompts[0].arguments == [
            {"name": "topic", "description": "the topic", "required": True}
        ]

    async def test_unsupported_family_is_skipped(self, provider):
        integ = self._integration(provider)
        session = FakeSession(
            tools=[_tool("only_tool")],
            resources=_Unsupported,
            prompts=_Unsupported,
        )
        provider._connections[integ.uuid] = FakeConnection(session)
        await provider._populate_resources(integ)
        # Tool loaded, resources/prompts absent, still marked loaded.
        assert integ.resources_loaded is True
        assert any(isinstance(r, MCPToolResource) for r in integ.resources.values())
        assert not any(isinstance(r, MCPResourceResource) for r in integ.resources.values())
        assert not any(isinstance(r, MCPPromptResource) for r in integ.resources.values())

    async def test_populate_resources_without_connection_raises(self, provider):
        integ = self._integration(provider)
        # No connection registered for this server.
        with pytest.raises(ValueError, match="Error initiating session"):
            await provider._populate_resources(integ)


# ---------------------------------------------------------------------------
# _populate_server_info
# ---------------------------------------------------------------------------


class TestPopulateServerInfo:
    async def _apply(self, integ, init_result):
        provider = _make_provider(config_paths=[])
        provider._connections[integ.uuid] = FakeConnection(init_result=init_result)
        await provider._populate_server_info(integ)

    async def test_populates_version_and_instructions(self):
        integ = MCPIntegration(name="s", description="", provider="mcp:mcp")
        # No config-derived description -> instructions adopted as description.
        integ.description = ""
        await self._apply(integ, _make_init_result(instructions="Use me wisely"))
        assert integ.server_version == "1.2.3"
        assert integ.instructions == "Use me wisely"
        assert integ.description == "Use me wisely"
        assert integ.extra_metadata["server_info"]["name"] == "srv"

    async def test_does_not_overwrite_curated_description(self):
        integ = MCPIntegration(name="s", description="curated", provider="mcp:mcp")
        await self._apply(integ, _make_init_result(instructions="server instructions"))
        assert integ.description == "curated"
        # Instructions still captured separately.
        assert integ.instructions == "server instructions"

    async def test_does_not_overwrite_curated_title(self):
        integ = MCPIntegration(
            name="s", description="d", provider="mcp:mcp", server_title="Curated"
        )
        await self._apply(integ, _make_init_result(serverInfo={"title": "From Server"}))
        assert integ.server_title == "Curated"

    async def test_raises_when_no_connection(self):
        integ = MCPIntegration(name="s", description="", provider="mcp:mcp")
        provider = _make_provider(config_paths=[])
        with pytest.raises(ValueError, match="Error loading server information"):
            await provider._populate_server_info(integ)


# ---------------------------------------------------------------------------
# Connection lifecycle (the _ServerConnection actor)
# ---------------------------------------------------------------------------


class TestConnectionLifecycle:
    async def test_ensure_connected_reuses_then_close_all(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")
        session = FakeSession(tools=[_tool("t")])
        with _fake_transport_and_session(provider, session):
            conn1 = await provider._ensure_connected(integ.uuid)
            conn2 = await provider._ensure_connected(integ.uuid)
            # Kept open and reused rather than reconnected per call.
            assert conn1 is conn2
            assert conn1.running
            # Ops run on the owner task against the live session.
            result = await conn1.run(lambda s: s.list_tools())
            assert [t.name for t in result.tools] == ["t"]
            await provider.close_all()
        assert not conn1.running
        assert provider._connections == {}

    async def test_disconnect_closes_single_connection(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")
        session = FakeSession()
        with _fake_transport_and_session(provider, session):
            conn = await provider._ensure_connected(integ.uuid)
            assert conn.running
            await provider.disconnect(integ.uuid)
        assert not conn.running
        assert integ.uuid not in provider._connections

    async def test_failed_start_not_cached(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")
        with patch.object(
            provider, "_open_transport", side_effect=RuntimeError("unreachable")
        ):
            with pytest.raises(RuntimeError, match="unreachable"):
                await provider._ensure_connected(integ.uuid)
        # A dead handle must not be cached; a later call gets to retry.
        assert integ.uuid not in provider._connections

    async def test_initialize_error_propagates_and_stops_task(self, json_config: Path):
        # An error during the handshake (here, session.initialize() raising)
        # must surface as the real exception and leave no running task behind --
        # not a silently-dead session that only denies later ops.
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")
        session = FakeSession(init_error=RuntimeError("handshake refused"))
        with _fake_transport_and_session(provider, session):
            conn = _ServerConnection(provider, integ)
            with pytest.raises(RuntimeError, match="handshake refused"):
                await conn.start()
            # The owner task unwound and stopped rather than lingering.
            assert not conn.running

    async def test_ensure_connected_initialize_error_not_cached(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")
        session = FakeSession(init_error=RuntimeError("handshake refused"))
        with _fake_transport_and_session(provider, session):
            with pytest.raises(RuntimeError, match="handshake refused"):
                await provider._ensure_connected(integ.uuid)
        assert integ.uuid not in provider._connections

    async def test_run_after_close_raises(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")
        session = FakeSession(tools=[_tool("t")])
        with _fake_transport_and_session(provider, session):
            conn = await provider._ensure_connected(integ.uuid)
            await provider.close_all()
            with pytest.raises(RuntimeError, match="not running"):
                await conn.run(lambda s: s.list_tools())


# ---------------------------------------------------------------------------
# Update / mutation
# ---------------------------------------------------------------------------


class TestUpdateIntegration:
    async def test_update_refreshes_in_memory_display_fields(self, json_config: Path):
        # Regression: updating a server must refresh the derived display fields
        # (name/server_title/description) on the in-memory integration, not just
        # rewrite the config file. Otherwise get_integration/list_integrations
        # return stale data until a new session re-discovers from disk.
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")

        provider.update_integration(
            integ.uuid,
            server_config={
                "name": integ.slug,
                "title": "Renamed FS",
                "description": "A freshly edited description.",
                "command": "npx",
                "transport": "stdio",
            },
        )
        await asyncio.sleep(0)  # let the scheduled disconnect task settle

        refreshed = provider.get_integration(integ.uuid)
        assert refreshed.name == "Renamed FS"
        assert refreshed.server_title == "Renamed FS"
        assert refreshed.description == "A freshly edited description."

    async def test_update_falls_back_to_name_when_no_title(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")

        provider.update_integration(
            integ.uuid,
            server_config={
                "name": integ.slug,
                "title": None,
                "command": "npx",
                "transport": "stdio",
            },
        )
        await asyncio.sleep(0)

        refreshed = provider.get_integration(integ.uuid)
        assert refreshed.name == integ.slug
        assert refreshed.description == f"MCP server '{integ.slug}'"


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------


class TestPrompt:
    def test_empty_when_no_servers(self):
        provider = _make_provider(config_paths=[])
        assert provider.prompt == ""

    def test_includes_server_and_tool(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")
        integ.resources_loaded = True
        integ.add_resources([
            MCPToolResource(
                integration=integ.uuid, tool_name="read_file", description="reads a file"
            )
        ])
        prompt = provider.prompt
        assert "filesystem" in prompt
        assert "read_file" in prompt
        assert "reads a file" in prompt
        # Usage instructions for the dispatch tools are present.
        assert "call_mcp_tool" in prompt


# ---------------------------------------------------------------------------
# Generic dispatch @tool methods
# ---------------------------------------------------------------------------


class TestListMcpTools:
    async def test_lists_cached_tools(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")
        integ.resources_loaded = True
        integ.add_resources([
            MCPToolResource(
                integration=integ.uuid,
                tool_name="read_file",
                description="reads",
                input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            )
        ])
        out = await MCPIntegrationProvider.list_mcp_tools(
            provider, server_slug="filesystem", agent=_agent_ref()
        )
        assert "read_file" in out
        assert "input schema" in out

    async def test_reports_unloaded_catalog(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        out = await MCPIntegrationProvider.list_mcp_tools(
            provider, server_slug="filesystem", agent=_agent_ref()
        )
        assert "could not be loaded" in out

    async def test_reports_no_tools(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")
        integ.resources_loaded = True
        out = await MCPIntegrationProvider.list_mcp_tools(
            provider, server_slug="filesystem", agent=_agent_ref()
        )
        assert "advertises no tools" in out

    async def test_unknown_slug_raises(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        with pytest.raises(ValueError, match="MCP server not found"):
            await MCPIntegrationProvider.list_mcp_tools(
                provider, server_slug="nope", agent=_agent_ref()
            )


class TestCallMcpTool:
    async def test_returns_flattened_content(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        session = FakeSession(
            call_result=SimpleNamespace(
                content=[SimpleNamespace(text="result text")], isError=False
            )
        )
        with _install_fake_connection(provider, session):
            out = await MCPIntegrationProvider.call_mcp_tool(
                provider,
                server_slug="filesystem",
                tool_name="read_file",
                arguments={"path": "/x"},
                agent=_agent_ref(),
            )
        assert out == "result text"
        assert session.calls == [("call_tool", "read_file", {"path": "/x"})]

    async def test_error_result_annotated(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        session = FakeSession(
            call_result=SimpleNamespace(
                content=[SimpleNamespace(text="bad path")], isError=True
            )
        )
        with _install_fake_connection(provider, session):
            out = await MCPIntegrationProvider.call_mcp_tool(
                provider,
                server_slug="filesystem",
                tool_name="read_file",
                arguments={},
                agent=_agent_ref(),
            )
        assert "returned an error" in out
        assert "bad path" in out

    async def test_empty_content_placeholder(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        session = FakeSession(
            call_result=SimpleNamespace(content=[], isError=False)
        )
        with _install_fake_connection(provider, session):
            out = await MCPIntegrationProvider.call_mcp_tool(
                provider,
                server_slug="filesystem",
                tool_name="noop",
                arguments=None,
                agent=_agent_ref(),
            )
        assert out == "(tool returned no content)"
        # None arguments coerced to an empty mapping on the wire.
        assert session.calls == [("call_tool", "noop", {})]

    async def test_keeps_connection_open_after_call(self, json_config: Path):
        # Kept-open model: a tool call must not tear the session down.
        provider = _make_provider(config_paths=[json_config])
        session = FakeSession(
            call_result=SimpleNamespace(content=[SimpleNamespace(text="x")], isError=False)
        )
        integ = provider._find_server_by_slug("filesystem")
        conn = FakeConnection(session)
        provider._connections[integ.uuid] = conn
        with patch.object(provider, "_ensure_connected", new=AsyncMock(return_value=conn)):
            await MCPIntegrationProvider.call_mcp_tool(
                provider,
                server_slug="filesystem",
                tool_name="t",
                arguments={},
                agent=_agent_ref(),
            )
        assert conn.closed is False


class TestReadMcpResource:
    async def test_returns_resource_contents(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        session = FakeSession(
            read_result=SimpleNamespace(contents=[SimpleNamespace(text="file body")])
        )
        with _install_fake_connection(provider, session):
            out = await MCPIntegrationProvider.read_mcp_resource(
                provider,
                server_slug="filesystem",
                uri="file:///a.txt",
                agent=_agent_ref(),
            )
        assert out == "file body"
        assert session.calls == [("read_resource", "file:///a.txt")]

    async def test_empty_resource_placeholder(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        session = FakeSession(read_result=SimpleNamespace(contents=[]))
        with _install_fake_connection(provider, session):
            out = await MCPIntegrationProvider.read_mcp_resource(
                provider,
                server_slug="filesystem",
                uri="file:///empty",
                agent=_agent_ref(),
            )
        assert out == "(resource is empty)"


# ---------------------------------------------------------------------------
# list/get accessors
# ---------------------------------------------------------------------------


class TestAccessors:
    def test_list_integrations(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        assert {i.slug for i in provider.list_integrations()} == {"filesystem", "deepwiki"}

    def test_get_integration_by_uuid(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")
        assert provider.get_integration(integ.uuid) is integ

    def test_get_integration_missing_raises(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        with pytest.raises(KeyError):
            provider.get_integration("no-such-uuid")

    async def test_list_resources_filtered_by_type(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")
        # Already-populated catalog: list_resources should not connect.
        integ.add_resources([
            MCPToolResource(integration=integ.uuid, tool_name="t"),
            MCPResourceResource(integration=integ.uuid, uri="u", name="n"),
        ])
        tools = await provider.list_resources(integ.uuid, resource_type="mcp_tool")
        assert len(tools) == 1
        assert isinstance(tools[0], MCPToolResource)

    async def test_list_resources_lazily_loads_when_empty(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")
        assert not integ.resources
        session = FakeSession(tools=[_tool("read_file", "reads")])
        with _install_fake_connection(provider, session):
            tools = await provider.list_resources(integ.uuid, resource_type="mcp_tool")
        assert integ.resources_loaded is True
        assert len(tools) == 1 and tools[0].tool_name == "read_file"

    async def test_list_resources_does_not_reload_when_populated(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")
        integ.add_resources([MCPToolResource(integration=integ.uuid, tool_name="t")])
        ensure = AsyncMock()
        with patch.object(provider, "_ensure_connected", new=ensure):
            await provider.list_resources(integ.uuid)
        ensure.assert_not_called()

    async def test_list_resources_propagates_connect_failure(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")
        with patch.object(
            provider, "_ensure_connected", new=AsyncMock(side_effect=RuntimeError("unreachable"))
        ):
            with pytest.raises(RuntimeError, match="unreachable"):
                await provider.list_resources(integ.uuid)
        assert not integ.resources

    def test_get_resource_missing_raises(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        integ = provider._find_server_by_slug("filesystem")
        with pytest.raises(KeyError):
            provider.get_resource(integ.uuid, "nope")

    def test_find_server_by_slug_missing_raises(self, json_config: Path):
        provider = _make_provider(config_paths=[json_config])
        with pytest.raises(ValueError, match="slug="):
            provider._find_server_by_slug("nope")

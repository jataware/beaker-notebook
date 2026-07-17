"""MCP (Model Context Protocol) servers exposed as Beaker integrations.

This module mirrors the structure of ``skill.py``: a single provider
(:class:`MCPIntegrationProvider`) discovers a set of MCP *servers* from a
config file (and/or convention directories), turns each server into an
:class:`MCPIntegration`, and exposes agent-facing tools for interacting with
them.

The mapping to the integration abstractions is:

    MCP server   -> Integration          (one integration per configured server)
    MCP tool     -> MCPToolResource       (callable; the primary primitive)
    MCP resource -> MCPResourceResource    (readable blob/text, addressed by URI)
    MCP prompt   -> MCPPromptResource       (parameterized prompt template)

Two things differ meaningfully from the skill provider and are the main
design decisions to settle before fleshing this out:

1. **Connection lifecycle.** Skills are static files read on demand. MCP
   servers are live processes/endpoints reached over a ``ClientSession``
   (stdio subprocess or streamable-HTTP), which is an anyio-based async
   context manager. Current approach (deliberately simple): at startup we
   connect to each server, fetch its tool/resource/prompt catalog, cache it,
   and immediately disconnect. Thereafter every tool invocation opens a fresh
   session for the duration of the call ("disconnect until use"). Startup
   catalog loading is synchronous/blocking for now; moving it to a background
   task is a known follow-up. See the OPEN QUESTIONS block at the bottom.

2. **Tool dispatch.** Skill "tools" are a fixed set of ``@tool`` methods that
   surface documentation. MCP tools are dynamic and are meant to be *invoked*.
   The base ``tools`` property only collects statically-decorated ``@tool``
   methods, so the simplest foundation is a small fixed set of generic
   dispatch tools (``list_mcp_tools`` / ``call_mcp_tool`` / ...). Registering
   each remote tool as its own first-class agent tool is possible but requires
   dynamic tool registration on the agent and is left as a follow-up.

NOTE: The dataclasses below are colocated here for reviewability. To match the
skill provider they'd likely move into ``integrations/types.py`` alongside the
``Skill*`` resource types once the shapes settle.
"""

import asyncio
import inspect
import io
import json
import logging
import os
import tempfile
import yaml
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, ClassVar, Literal, Mapping, Optional
from typing_extensions import Self

from archytas.tool_utils import tool, AgentRef
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client, create_mcp_http_client
from pydantic import AnyUrl

from beaker_notebook.lib.autodiscovery import find_resource_dirs
from beaker_notebook.lib.integrations.types import Integration, Resource
from .base import BaseIntegrationProvider, MutableBaseIntegrationProvider

if TYPE_CHECKING:
    import httpx
    from beaker_notebook.lib.agent import BeakerAgent
    from beaker_notebook.lib.context import BeakerContext
    from mcp.types import InitializeResult

logger = logging.getLogger(__name__)


def _json_schema_type(spec: dict[str, Any]) -> str:
    """Best-effort human-readable type string for a JSON-Schema property.

    Handles the common shapes seen in MCP tool schemas: a plain ``type``, a
    union via ``anyOf``/``oneOf``, and enums. Falls back to ``"any"``.
    """
    if "type" in spec:
        type_val = spec["type"]
        if isinstance(type_val, list):
            return "|".join(str(t) for t in type_val)
        return str(type_val)
    for union_key in ("anyOf", "oneOf"):
        if union_key in spec and isinstance(spec[union_key], list):
            return "|".join(_json_schema_type(s if isinstance(s, dict) else {}) for s in spec[union_key])
    if "enum" in spec:
        return "enum"
    return "any"


@asynccontextmanager
async def _streamable_http_transport(url: str, client: "httpx.AsyncClient"):
    """Adapt ``streamable_http_client`` to a caller-owned httpx client.

    The current ``streamable_http_client`` no longer accepts ``headers``/``auth``/
    ``timeout`` kwargs (that shape is the deprecated ``streamablehttp_client``);
    HTTP settings are configured on an ``httpx.AsyncClient`` handed in via
    ``http_client``. It also does not close a client passed to it, so the caller
    that created the client owns its lifecycle. Wrapping both in one context
    manager keeps the client and the transport entered/exited together on the
    owner task (see ``_ServerConnection``'s same-task invariant).
    """
    async with client:
        async with streamable_http_client(url, http_client=client) as streams:
            yield streams


# ---------------------------------------------------------------------------
# Config schema  (parsed from mcp.json / .mcp.json)
#
# Follows the conventional `mcpServers` layout used by other MCP hosts:
#
#   {
#     "mcpServers": {
#       "filesystem": {
#         "command": "npx",
#         "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"],
#         "env": {"FOO": "bar"}
#       },
#       "remote-api": {
#         "type": "http",
#         "url": "https://example.com/mcp",
#         "headers": {"Authorization": "Bearer ..."}
#       }
#     }
#   }
# ---------------------------------------------------------------------------

MCPTransport = Literal["stdio", "http", "sse"]


@dataclass(kw_only=True)
class MCPServerConfig:
    """One entry from a MCP mapping.

    The transport is autodetected: presence of ``command`` implies ``stdio``;
    presence of ``url`` implies ``http`` (or ``sse`` when explicitly set).
    """
    name: str
    title: Optional[str] = None
    # stdio transport
    command: Optional[str] = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # http/sse transport
    url: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)
    # explicit override; otherwise inferred from command/url
    transport: Optional[MCPTransport] = None
    disabled: bool = False
    config_file: Optional[str] = None
    cached_resources: Optional[dict[str, list[str]]] = None

    description: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    @property
    def resolved_transport(self) -> MCPTransport:
        if self.transport is not None:
            return self.transport
        if self.command:
            return "stdio"
        if self.url:
            return "http"
        raise ValueError(f"MCP server '{self.name}' has neither command nor url")

    @classmethod
    def from_dict(cls, name: str, data: dict, config_file: Optional[str] = None) -> "MCPServerConfig":
        metadata = data.get("x-beaker-notebook") or {}
        title = data.get("title") or metadata.get("title")
        description = data.get("description") or metadata.get("description") or None
        cached_resources = data.get("known_resources", None)
        return cls(
            name=name,
            title=title,
            command=data.get("command"),
            args=list(data.get("args") or []),
            env=dict(data.get("env") or {}),
            url=data.get("url"),
            headers=dict(data.get("headers") or {}),
            transport=data.get("type") or data.get("transport"),
            disabled=bool(data.get("disabled", False)),
            config_file=config_file,
            cached_resources=cached_resources,
            description=description,
            metadata=metadata,
        )

    def to_config_dict(self):
        data = dict(
            name=self.name,
            title=self.title,
            cached_resources=self.cached_resources,
            description=self.description,
        )
        if self.command:
            data["command"] = self.command
        if self.args:
            data["args"] = self.args
        if self.env:
            data["env"] = self.env
        if self.url:
            data["url"] = self.url
        if self.headers:
            data["headers"] = self.headers
        if self.transport:
            data["transport"] = self.transport
        if self.disabled:
            data["disabled"] = self.disabled
        if self.metadata:
            data["x-beaker-notebook"] = self.metadata
        return data

    def update(self, data: dict|Self) -> None:
        if isinstance(data, dict):
            data = self.from_dict(self.name, data)
        for key in ("name", "title", "command", "args", "description", "cached_resources", "env", "url", "transport"):
            if not hasattr(data, key):
                continue
            data_val = getattr(data, key, None)
            if data_val != getattr(self, key, None):
                setattr(self, key, data_val)

    def update_config_file(self):
        config_path = self.config_file
        if not config_path or not os.path.isfile(self.config_file):
            raise FileNotFoundError(f"Unable to update file {self.config_file} as it cannot be found.")

        # Read, update and write config file in one block to hold lock on file
        with open(config_path, "r+") as f:
            if config_path.name.endswith('.json'):
                data = json.load(f)
            elif config_path.name.endswith(('.yaml', '.yml')):
                data = yaml.safe_load(f.read())

            root_name = "servers" if "servers" in data else "mcpServers" if "mcpServers" in data else "servers"
            root = data.setdefault(root_name, {})
            root[self.name] = self.to_config_dict()

            f.seek(0)
            f.truncate(0)
            if config_path.name.endswith('.json'):
                json.dump(data, f, indent=2)
            elif config_path.name.endswith(('.yaml', '.yml')):
                yaml.safe_dump(data, f)


# ---------------------------------------------------------------------------
# Resources  (mirror the three MCP server primitives)
# ---------------------------------------------------------------------------

@dataclass(kw_only=True)
class MCPToolResource(Resource):
    """A tool advertised by an MCP server (the primary, callable primitive)."""
    resource_type: str = "mcp_tool"
    tool_name: str
    description: Optional[str] = None
    # JSON Schema for the tool's arguments, as returned by tools/list.
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True)
class MCPResourceResource(Resource):
    """A readable resource advertised by an MCP server (addressed by URI)."""
    resource_type: str = "mcp_resource"
    uri: str
    name: str
    description: Optional[str] = None
    mime_type: Optional[str] = None
    # Fetched on demand via resources/read.
    content: Optional[str] = None


@dataclass(kw_only=True)
class MCPPromptResource(Resource):
    """A prompt template advertised by an MCP server."""
    resource_type: str = "mcp_prompt"
    prompt_name: str
    description: Optional[str] = None
    # Argument descriptors from prompts/list.
    arguments: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MCPIntegration(Integration):
    """An integration backed by a single MCP server."""
    datatype: str = "mcp"  # IntegrationTypes literal includes "mcp"
    # The config used to (re)establish the connection.
    server_config: Optional[MCPServerConfig] = None
    # Whether a live ClientSession currently exists for this server. Transient:
    # true only while a connection is open (during catalog load or a tool call).
    connected: bool = False
    # Whether the tool/resource/prompt catalog has been fetched and cached into
    # `resources`. Persists across (dis)connects — the catalog outlives any
    # individual session. Distinct from `connected` because we eagerly load the
    # catalog at startup and then drop the connection until a tool is invoked.
    resources_loaded: bool = False

    # --- Identity reported by the server via session.initialize() -------
    # MCP has no generic per-server "description" field; the closest is the
    # top-level `instructions` string, which we also use as `description`
    # (see Integration.description) when the server provides one. The base
    # Integration.url / Integration.img_url fields hold the server's
    # websiteUrl / first icon when advertised. Raw serverInfo and init meta
    # are stashed in Integration.extra_metadata under "server_info" / "init_meta".
    server_title: Optional[str] = None      # serverInfo.title (human-friendly)
    server_version: Optional[str] = None    # serverInfo.version
    instructions: Optional[str] = None      # top-level init instructions
    capabilities: dict[str, Any] = field(default_factory=dict)  # advertised capabilities


# ---------------------------------------------------------------------------
# Session ownership
# ---------------------------------------------------------------------------

# An operation to run against a live session. Callers express "what to do with
# the session" as a closure; it is awaited on the owner task (see below).
Op = Callable[[ClientSession], Awaitable[Any]]


class _ServerConnection:
    """Owns a single MCP server's live session on one long-lived task.

    The transport and ``ClientSession`` context managers each open an anyio task
    group whose cancel scope is pinned to the task that entered it; anyio
    requires it be exited on that same task. A kept-open session therefore
    cannot be opened on one task (e.g. an HTTP handler populating the catalog)
    and torn down on another (e.g. the agent loop invoking a tool) -- doing so
    raises "Attempted to exit cancel scope in a different task".

    This class confines the entire session lifecycle -- connect, every request,
    and disconnect -- to a single dedicated task (``_task``). Callers on any
    task submit an :data:`Op` via :meth:`run` and await its result over a
    per-request future; the queue and futures are loop-bound but task-agnostic,
    so cross-task hand-off is safe as long as everyone shares one event loop.

    Requests are serialized: one op runs to completion before the next starts.
    """

    def __init__(self, provider: "MCPIntegrationProvider", integration: MCPIntegration):
        self._provider = provider
        self._integration = integration
        self._queue: "asyncio.Queue[tuple[Optional[Op], asyncio.Future]]" = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._ready: asyncio.Future = asyncio.get_running_loop().create_future()
        self.init_result: Optional["InitializeResult"] = None
        # stderr capture for the subprocess (stdio transport); set once the
        # transport is opened. Stays None if we fail before opening it.
        self.logfile = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Spawn the owner task and return once the handshake succeeds.

        Propagates any connect/initialize error to the caller (via ``_ready``).
        """
        self._task = asyncio.create_task(
            self._run(),
            name=f"mcp-session:{self._integration.slug}"
        )

        try:
            await asyncio.wait_for(self._ready, timeout=120)
        except TimeoutError:
            # Cancel task and running service if we are not ready in time
            self._task.cancel()
            raise


    async def _run(self) -> None:
        """Own the session end-to-end on this task until asked to close."""
        config = self._integration.server_config
        try:
            async with AsyncExitStack() as stack:  # entered on THIS task
                # Connect + handshake. Catch failures here, before they unwind
                # *through* the transport/ClientSession context managers with an
                # active exception in flight -- anyio's task-group teardown under
                # an in-flight exception is where the original error can get
                # masked or wrapped. Instead we record the failure on `_ready`
                # and return, so the stack exits via the normal (no-exception)
                # path and `start()` sees the real cause.
                try:
                    transport, logfile = self._provider._open_transport(config)
                    self.logfile = logfile
                    streams = await stack.enter_async_context(transport)
                    session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
                    self.init_result = await session.initialize()
                except BaseException as exc:  # noqa: BLE001 - relayed via _ready
                    # We may have failed before the transport (and thus the
                    # stderr capture) was opened -- e.g. an invalid config -- so
                    # only surface captured stderr when we actually have some.
                    if self.logfile is not None:
                        self.logfile.seek(0)
                        proc_stderr = self.logfile.read().decode(errors="replace")
                        if proc_stderr:
                            exc.add_note(f"Subprocess stderr:\n{proc_stderr}")
                    self._ready.set_exception(exc)
                    return  # -> stack unwinds cleanly here, on THIS task
                self._integration.connected = True
                self._ready.set_result(None)  # handshake done; callers may proceed

                while True:
                    op, fut = await self._queue.get()
                    if op is None:  # shutdown sentinel
                        if not fut.done():
                            fut.set_result(None)
                        break  # -> stack unwinds here, on THIS task
                    try:
                        result = await op(session)
                    except Exception as exc:  # noqa: BLE001 - relayed to the caller
                        if not fut.done():
                            fut.set_exception(exc)
                    else:
                        if not fut.done():
                            fut.set_result(result)
        except BaseException as exc:  # the transport died mid-loop
            # Startup failures are handled above (via `_ready`) and return before
            # reaching here, so at this point `_ready` is always resolved; this
            # path only covers a session that dies after a successful handshake.
            self._fail_pending(exc)
        finally:
            self._integration.connected = False
            # Nothing can run these now (the session is gone); don't let a
            # caller that raced past the shutdown sentinel await forever.
            self._fail_pending(RuntimeError(
                f"MCP session for '{self._integration.slug}' is closed"
            ))

    def _fail_pending(self, exc: BaseException) -> None:
        """Fail any queued (and not-yet-run) requests once the session is gone."""
        while not self._queue.empty():
            _op, fut = self._queue.get_nowait()
            if not fut.done():
                fut.set_exception(exc)

    async def run(self, op: Op) -> Any:
        """Submit ``op`` to the owner task and await its result."""
        if not self.running:
            raise RuntimeError(
                f"MCP session for '{self._integration.slug}' is not running"
            )
        fut = asyncio.get_running_loop().create_future()
        self._queue.put_nowait((op, fut))
        return await fut

    async def close(self) -> None:
        """Ask the owner task to tear the session down, and wait for it."""
        if not self.running:
            return
        fut = asyncio.get_running_loop().create_future()
        self._queue.put_nowait((None, fut))  # sentinel; drains the stack on the owner task
        await self._task


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class MCPIntegrationProvider(MutableBaseIntegrationProvider):
    """Provides MCP servers as Beaker integrations.

    Servers are discovered from ``mcp.json`` config files (conventional
    ``mcpServers`` layout) found under the same search roots the skill
    provider uses. Each server becomes an :class:`MCPIntegration`; its tools,
    resources, and prompts become the integration's resources once a session
    is established.
    """

    provider_type: ClassVar[str] = "mcp"
    display_name: ClassVar[str] = "MCP Servers"
    slug: ClassVar[str] = "mcp"

    def __init__(
        self,
        id: Optional[str] = None,
        config_paths: Optional[list[str | os.PathLike]] = None,
    ):
        super().__init__(id=id)
        logger.debug(f"Initializing MCPIntegrationProvider {self.display_name} ({self.id})")
        self._servers: list[MCPIntegration] = list(
            self.discover_integrations(paths=config_paths, corpus=self.id).values()
        )
        # Kept-open sessions keyed by integration uuid. Each entry is an actor
        # that owns one server's session on a dedicated task; connections are
        # established lazily on first use and reused thereafter. See
        # `_ServerConnection`, `_ensure_connected`, and `disconnect`.
        self._connections: dict[str, _ServerConnection] = {}

    # --- Discovery -------------------------------------------------------

    async def cleanup(self):
        await self.close_all()

    @classmethod
    def from_context(cls, context: "BeakerContext") -> list[Self]:
        context_dir_path = Path(inspect.getabsfile(context.__class__)).parent
        integration_paths = cls.discover_integration_paths(root_paths=[context_dir_path])
        if integration_paths:
            return [cls(id=f"context-{context.slug}", config_paths=integration_paths)]
        else:
            return []

    @classmethod
    def _get_config_search_roots(cls) -> list[Path]:
        """Base dirs to search for MCP config, most-specific first.

        Mirrors ``SkillIntegrationProvider._get_skill_search_roots``:
        project-level (``./.agents``, ``./.beaker``), user-level
        (``~/.agents``, ``~/.beaker``), then autodiscovery data dirs.
        """
        roots: list[Path] = []
        seen: set[Path] = set()

        def _add(p: Path):
            try:
                resolved = p.resolve()
            except OSError:
                resolved = p
            if resolved in seen or not p.is_dir():
                return
            seen.add(resolved)
            roots.append(p)

        _add(Path.cwd())
        for name in (".agents", ".beaker"):
            _add(Path.cwd() / name)
        for name in (".agents", ".beaker"):
            _add(Path.home() / name)
        for data_dir in find_resource_dirs("data"):
            _add(Path(data_dir))
        return roots

    @classmethod
    def discover_integration_paths(
        cls, root_paths: Optional[list[str | os.PathLike]] = None
    ) -> list[Path]:
        """Locate MCP config files within the given roots.

        Each root directory is scanned for the recognized config filenames
        (``mcp.json``, ``.mcp.json``, ``mcp.yaml``, ...); a root that points
        directly at a file is returned as-is. When ``root_paths`` is ``None``
        the conventional config search roots are used. Returns the config file
        paths in discovery order; does not read or parse them.
        """
        roots = cls._get_config_search_roots() if root_paths is None else [Path(p) for p in root_paths]
        config_files: list[Path] = []
        for root in roots:
            if root.is_file():
                config_files.append(root)
                continue
            if not root.is_dir():
                continue
            for fname in ("mcp.json", ".mcp.json", "mcp.yml", ".mcp.yml", "mcp.yaml", ".mcp.yaml"):
                candidate = root / fname
                if candidate.is_file():
                    config_files.append(candidate)
        return config_files

    @classmethod
    def discover_integrations(
        cls, *, paths: Optional[list[str | os.PathLike]] = None, corpus: Optional[str] = None, **kwargs
    ) -> Mapping[str, MCPIntegration]:
        """Discover MCP servers from ``mcp.json`` files under each root.

        Does NOT connect to any server; discovery only parses config and
        builds :class:`MCPIntegration` shells. Tool/resource/prompt discovery
        happens on connect().
        """
        integrations: dict[str, MCPIntegration] = {}
        seen_names: set[str] = set()

        for config_path in cls.discover_integration_paths(paths):
            try:
                with open(config_path) as f:
                    if config_path.name.endswith('.json'):
                        data = json.load(f)
                    elif config_path.name.endswith(('.yaml', '.yml')):
                        data = yaml.safe_load(f.read())
                    else:
                        raise RuntimeError("Unable to read configuration file: Unknown extension.")
            except Exception:
                logger.exception("Failed to read MCP config at %s", config_path)
                continue

            servers = (data.get("servers") or data.get("mcpServers")) if isinstance(data, dict) else None

            if not isinstance(servers, dict):
                logger.warning("MCP config %s missing 'mcpServers' mapping", config_path)
                continue

            for name, server_data in servers.items():
                if name in seen_names:
                    logger.debug("Skipping duplicate MCP server '%s' from %s", name, config_path)
                    continue
                try:
                    server_config = MCPServerConfig.from_dict(name, server_data, config_file=config_path)
                    if server_config.disabled:
                        continue
                    integration = cls._build_integration(server_config, corpus=corpus)
                    seen_names.add(name)
                    integrations[integration.uuid] = integration
                except Exception:
                    logger.exception("Failed to load MCP server '%s' from %s", name, config_path)

        return integrations

    @classmethod
    def _build_integration(cls, server_config: MCPServerConfig, corpus: Optional[str] = None) -> MCPIntegration:
        """Build the (unconnected) integration shell for a server config.

        Resources are populated later, on connect(), from the server's
        tools/list, resources/list, and prompts/list responses.
        """

        uuid = f"{cls.slug}:{corpus}:{server_config.name}"
        display_name = server_config.title or server_config.name
        provider_ref = f"{cls.provider_type}:{cls.slug}"
        description = server_config.description or f"MCP server '{server_config.name}'"
        return MCPIntegration(
            uuid=uuid,
            slug=server_config.name,
            server_title=server_config.title,
            name=display_name,
            description=description,
            provider=provider_ref,
            server_config=server_config,
            corpus=corpus,
        )

    @classmethod
    def _merge(cls, a: Self, b: Self) -> Self:
        existing = {s.name for s in a._servers}
        for server in b._servers:
            if server.name not in existing:
                a._servers.append(server)
        return a

    # --- Connection lifecycle -------------------------------------------

    def _open_transport(self, config: MCPServerConfig):
        """Return the (unentered) transport async context manager for a config.

        The returned object yields a ``(read_stream, write_stream, ...)`` tuple
        when entered; stdio/sse yield a 2-tuple and streamable-http yields a
        3-tuple (the third element is a session-id accessor we don't use).
        """
        transport = config.resolved_transport
        if transport == "stdio":
            if not config.command:
                raise ValueError(f"MCP server '{config.name}' has no command for stdio transport")
            log_file = tempfile.TemporaryFile()
            logger.warning(f"Logging to file {log_file=}")
            params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env or None,
            )
            return (stdio_client(params, errlog=log_file), log_file)
        if transport == "http":
            if not config.url:
                raise ValueError(f"MCP server '{config.name}' has no url for http transport")
            client = create_mcp_http_client(headers=config.headers or None)
            # Network transports have no subprocess, so there is no captured
            # stderr; hand back an empty buffer to satisfy the
            # (transport, logfile) contract expected by _ServerConnection._run.
            return (_streamable_http_transport(config.url, client), io.BytesIO())
        if transport == "sse":
            if not config.url:
                raise ValueError(f"MCP server '{config.name}' has no url for sse transport")
            return sse_client(config.url, headers=config.headers or None)
        raise ValueError(f"Unsupported MCP transport: {transport!r}")

    async def _ensure_connected(self, integration_id: str) -> _ServerConnection:
        """Return a live, kept-open connection for a server, starting it lazily.

        The first call spins up the server's owner task and blocks until the
        initialize handshake completes; subsequent calls reuse the same warm
        connection. A failed/exited connection is not cached, so a later call
        retries a fresh one.
        """
        conn = self._connections.get(integration_id)
        if conn is not None and conn.running:
            return conn

        integration = self.get_integration(integration_id)
        if integration.server_config is None:
            raise ValueError(f"MCP integration '{integration.name}' has no server config")

        conn = _ServerConnection(self, integration)
        self._connections[integration_id] = conn
        try:
            await conn.start()
        except BaseException:
            # Don't leave a dead handle cached; the next call will retry.
            self._connections.pop(integration_id, None)
            raise
        return conn

    async def disconnect(self, integration_id: str) -> None:
        """Tear down the kept-open session for an integration, if any."""
        conn = self._connections.pop(integration_id, None)
        if conn is not None:
            await conn.close()

    async def close_all(self) -> None:
        """Tear down every open session. Call on provider/context shutdown."""
        conns = list(self._connections.values())
        self._connections.clear()
        results = await asyncio.gather(*(asyncio.wait_for(c.close(), timeout=3) for c in conns), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException) or (isinstance(result, type) and issubclass(result, BaseException)):
                logger.exception("There was an error when attempting to close an MCP connection", exc_info=result)


    # --- Catalog population ----------------------------------------------

    async def _populate_server_info(self, integration: MCPIntegration) -> None:
        """Populate integration identity from a session.initialize() result.

        MCP exposes no generic server "description"; when the server provides
        top-level ``instructions`` we adopt them as the integration's
        description (leaving the config-derived default in place otherwise).
        """
        conn = self._connections.get(integration.uuid)
        init_result = conn.init_result if conn is not None else None
        if init_result is None:
            raise ValueError("Error loading server information from MCP server.")

        info = init_result.serverInfo
        # Don't overwrite a curated title even if one is provided by the service
        if info.title and not integration.server_title:
            integration.server_title = info.title
        if info.version:
            integration.server_version = info.version
        if info.websiteUrl:
            integration.url = str(info.websiteUrl)
        if info.icons:
            integration.img_url = str(info.icons[0].src)

        integration.instructions = init_result.instructions
        # Don't overwrite a curated description
        if init_result.instructions and not integration.description:
            integration.description = init_result.instructions

        integration.capabilities = init_result.capabilities.model_dump(exclude_none=True)

        # Preserve the raw serverInfo (incl. the server's self-reported name,
        # which may differ from the config handle) and any init meta for
        # callers that want fields we haven't lifted to typed attributes.
        integration.extra_metadata["server_info"] = info.model_dump(mode="json")
        if init_result.meta:
            integration.extra_metadata["init_meta"] = init_result.meta

    async def _populate_resources(self, integration: MCPIntegration) -> None:
        """Fetch tools/resources/prompts from a live session into the integration.

        Each primitive family is fetched independently: servers commonly
        implement only a subset (e.g. tools but not prompts), and unsupported
        families surface as errors we can safely skip.
        """
        conn = self._connections.get(integration.uuid)
        if conn is None or not conn.running:
            raise ValueError(f"Error initiating session with MCP integration '{integration.name} ({integration.slug})'")
        try:
            tools_result = await conn.run(lambda s: s.list_tools())
            for mcp_tool in tools_result.tools:
                integration.add_resources([MCPToolResource(
                    integration=integration.uuid,
                    tool_name=mcp_tool.name,
                    description=mcp_tool.description,
                    input_schema=mcp_tool.inputSchema or {},
                )])
        except Exception:
            logger.debug("MCP server '%s' tools/list failed", integration.name, exc_info=True)

        try:
            resources_result = await conn.run(lambda s: s.list_resources())
            for mcp_resource in resources_result.resources:
                integration.add_resources([MCPResourceResource(
                    integration=integration.uuid,
                    uri=str(mcp_resource.uri),
                    name=mcp_resource.name,
                    description=mcp_resource.description,
                    mime_type=mcp_resource.mimeType,
                )])
        except Exception:
            logger.debug("MCP server '%s' resources/list failed", integration.name, exc_info=True)

        try:
            prompts_result = await conn.run(lambda s: s.list_prompts())
            for mcp_prompt in prompts_result.prompts:
                integration.add_resources([MCPPromptResource(
                    integration=integration.uuid,
                    prompt_name=mcp_prompt.name,
                    description=mcp_prompt.description,
                    arguments=[
                        {"name": arg.name, "description": arg.description, "required": arg.required}
                        for arg in (mcp_prompt.arguments or [])
                    ],
                )])
        except Exception:
            logger.debug("MCP server '%s' prompts/list failed", integration.name, exc_info=True)

        integration.resources_loaded = True

    # --- Abstract method implementations --------------------------------

    def list_integrations(self) -> list[Integration]:
        return list(self._servers)

    def get_integration(self, integration_id: str) -> MCPIntegration:
        for server in self._servers:
            if server.uuid == integration_id:
                return server
        raise KeyError(f"MCP integration not found: {integration_id}")

    async def list_resources(self, integration_id: str, resource_type: Optional[str] = None) -> list[Resource]:
        server = self.get_integration(integration_id)
        # Lazily (re)populate the catalog on first view. The eager startup load
        # may have failed (e.g. the server was unreachable at the time); retry
        # here so the UI can either display the catalog or surface a failure. A
        # failed connect propagates to the caller, which distinguishes it from a
        # reachable server that simply advertises nothing.
        if not server.resources:
            await self._ensure_connected(integration_id)
            await self._populate_server_info(server)
            await self._populate_resources(server)
        resources = list(server.resources.values())
        if resource_type:
            resources = [r for r in resources if r.resource_type == resource_type]
        return resources

    def get_resource(self, integration_id: str, resource_id: str) -> Resource:
        server = self.get_integration(integration_id)
        if resource_id not in server.resources:
            raise KeyError(f"Resource not found: {resource_id}")
        return server.resources[resource_id]


    # --- Mutation method implementations --------------------------------
    # These methods only ever modify local MCP files.

    def add_integration(self, **payload) -> Integration:
        """Persist a new, locally-configured MCP server.

        The frontend sends the connection details under ``server_config`` (with
        display ``title``/``description`` folded in); we build a
        :class:`MCPServerConfig`, attach it to a writable config file, register
        the integration, and write it out. Returns the new integration so the
        UI can select it.
        """
        config_dict = payload.get("server_config")
        if not config_dict:
            raise ValueError("Cannot add MCP integration: no server config provided.")

        name = config_dict.get("name") or payload.get("slug") or payload.get("name")
        if not name:
            raise ValueError("Cannot add MCP integration: no server name provided.")

        if any(server.slug == name for server in self._servers):
            raise ValueError(f"An MCP server named '{name}' already exists.")

        server_config = MCPServerConfig.from_dict(name, config_dict)
        server_config.config_file = self._ensure_writable_config_file()

        integration = self._build_integration(server_config, corpus=self.id)
        self._servers.append(integration)
        server_config.update_config_file()
        return integration

    def _ensure_writable_config_file(self) -> Path:
        """Resolve (and create, if needed) a config file to persist a new server.

        Prefers a config file this provider already reads from and can write to,
        so a user's servers stay collected in one place; otherwise falls back to
        a conventional user-level ``~/.beaker/mcp.json``, scaffolding an empty
        ``mcpServers`` mapping when the file does not yet exist.
        """
        for server in self._servers:
            cfg = server.server_config
            if cfg is not None and cfg.config_file:
                path = Path(cfg.config_file)
                if path.is_file() and os.access(path, os.W_OK):
                    return path

        target = Path.home() / ".beaker" / "mcp.json"
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w") as f:
                json.dump({"mcpServers": {}}, f, indent=2)
        return target

    def update_integration(self, integration_id: str, **payload) -> Integration:
        config_dict = payload.get("server_config", None)
        if not config_dict:
            raise ValueError("Cannot save integration as server config not found.")

        def disconnnect_callback(task: asyncio.Task):
            err = task.exception()
            if err:
                logger.exception(f"Error shutting down integration '{integration_id}", exc_info=err)

        # Disconnect any running connection so that it will reconnect using the new configuration at next use
        loop = asyncio.get_event_loop()
        disconnect_task = loop.create_task(self.disconnect(integration_id))
        disconnect_task.add_done_callback(disconnnect_callback)

        server = self.get_integration(integration_id)
        server_config = server.server_config
        server_config.update(config_dict)
        cached_resources = defaultdict(list)
        for _res_id, resource in payload.get("resources", {}).items():
            res_type = resource.get("resource_type")
            match res_type:
                case "mcp_tool":
                    name = resource.get("tool_name")
                case "mcp_resource":
                    name = resource.get("name")
                case "mcp_prompt":
                    name = resource.get("prompt_name")
                case _:
                    pass
            if name:
                cached_resources[res_type].append(name)
        if cached_resources:
            server_config.cached_resources = dict(cached_resources)
        server_config.update_config_file()
        return server

    def remove_integration(self, integration_id: str, **payload) -> None:
        raise NotImplementedError()

    def add_resource(self, integration_id: str, **payload) -> Resource:
        raise NotImplementedError()

    def update_resource(self, integration_id: str, resource_id: str, **payload) -> Resource:
        raise NotImplementedError()

    def remove_resource(self, integration_id: str, resource_id: str, **payload) -> None:
        raise NotImplementedError()

    # --- Prompt (Tier 1: server + catalog listing, as YAML) ------------

    @property
    def prompt(self) -> str:
        if not self._servers:
            return ""
        usage = [
            "Use connect_to_mcp_server(server_slug) to connect to a MCP server and retreive full server details and resources.",
            "Use call_mcp_tool(server_slug, tool_name, arguments) to invoke a tool.",
            "Use read_mcp_resource(server_slug, uri) to read a resource. ",
            "Use list_mcp_tools(server_slug) to re-lists a server's tools on demand.",
        ]
        data = {
            "usage": usage,
            "servers": [self._server_to_dict(s) for s in self._servers],
        }
        yaml_text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False).rstrip("\n")
        return f"""
```yaml
{yaml_text}
```
        """.strip()

    def _server_to_dict(self, server: MCPIntegration) -> dict[str, Any]:
        """Render a single server (and its cached catalog) as a plain dict."""
        entry: dict[str, Any] = {
            "slug": server.slug,
            "name": server.name,
        }
        if server.server_title:
            entry["title"] = server.server_title
        if server.server_version:
            entry["version"] = server.server_version
        entry["description"] = server.description or ""

        tools = [r for r in server.resources.values() if isinstance(r, MCPToolResource)]
        resources = [r for r in server.resources.values() if isinstance(r, MCPResourceResource)]
        prompts = [r for r in server.resources.values() if isinstance(r, MCPPromptResource)]

        if tools:
            entry["tools"] = [self._tool_to_dict(t) for t in tools]
        if resources:
            entry["resources"] = [self._resource_to_dict(r) for r in resources]
        if prompts:
            entry["prompts"] = [self._prompt_to_dict(p) for p in prompts]

        return entry

    def _tool_to_dict(self, t: MCPToolResource) -> dict[str, Any]:
        entry: dict[str, Any] = {"tool_name": t.tool_name}
        if t.description:
            entry["description"] = t.description
        return entry

    def _resource_to_dict(self, r: MCPResourceResource) -> dict[str, Any]:
        entry: dict[str, Any] = {"uri": r.uri, "name": r.name}
        if r.mime_type:
            entry["mime_type"] = r.mime_type
        if r.description:
            entry["description"] = r.description
        return entry

    def _prompt_to_dict(self, p: MCPPromptResource) -> dict[str, Any]:
        entry: dict[str, Any] = {"prompt_name": p.prompt_name}
        if p.description:
            entry["description"] = p.description
        return entry

    @staticmethod
    def _schema_arguments_to_dict(input_schema: dict[str, Any]) -> Optional[list[dict[str, Any]]]:
        """Render a tool's JSON-Schema arguments as a list of argument dicts.

        Returns None when the schema declares no properties, so the caller can
        omit the key entirely.
        """
        properties = (input_schema or {}).get("properties") or {}
        if not properties:
            return None
        required = set((input_schema or {}).get("required") or [])
        args: list[dict[str, Any]] = []
        for name, spec in properties.items():
            spec = spec if isinstance(spec, dict) else {}
            arg: dict[str, Any] = {
                "name": str(name),
                "type": _json_schema_type(spec),
                "required": name in required,
            }
            desc = spec.get("description")
            if desc:
                arg["description"] = str(desc)
            args.append(arg)
        return args

    # --- Helpers ---------------------------------------------------------

    def _find_server_by_name(self, server_name: str) -> MCPIntegration:
        for server in self._servers:
            if server.name == server_name:
                return server
        raise ValueError(f"MCP server not found: {server_name}")

    def _find_server_by_slug(self, server_slug: str) -> MCPIntegration:
        for server in self._servers:
            if server.slug == server_slug:
                return server
        raise ValueError(f"MCP server not found: slug={server_slug}")

    def _get_session_id(self, agent: "BeakerAgent") -> str:
        return agent.context.subkernel.kernel_id

    @staticmethod
    def _flatten_content(blocks: Any) -> str:
        """Flatten MCP content blocks (tool results) into text.

        Text blocks contribute their text; non-text blocks (image, audio,
        embedded resources) are rendered as a short placeholder so the agent
        at least knows they were returned.
        """
        parts: list[str] = []
        for block in blocks or []:
            text = getattr(block, "text", None)
            if text is not None:
                parts.append(text)
            else:
                block_type = getattr(block, "type", type(block).__name__)
                parts.append(f"<non-text content block: {block_type}>")
        return "\n".join(parts)

    @staticmethod
    def _flatten_resource_contents(contents: Any) -> str:
        """Flatten the contents of a resources/read result into text."""
        parts: list[str] = []
        for item in contents or []:
            text = getattr(item, "text", None)
            if text is not None:
                parts.append(text)
                continue
            blob = getattr(item, "blob", None)
            if blob is not None:
                mime = getattr(item, "mimeType", None) or "application/octet-stream"
                parts.append(f"<binary resource ({mime}), {len(blob)} base64 chars>")
            else:
                parts.append(repr(item))
        return "\n".join(parts)

    # --- Tools (generic dispatch) ---------------------------------------

    @tool(internal=True)
    async def connect_to_mcp_server(self, server_slug: str, agent: AgentRef) -> str:
        """
        Connects to a server and returns full information about the MCP server and its capabilities.

        Call this once you have selected a MCP server to use, prior to using it, to load the relevent
        details into context.
        You may also call this to

        Args:
            server_slug: The slug of the MCP server (as shown in the provider listing).

        Returns:
            str: A full description of the server with full instructions, tools, and resources enumerated.
        """
        server = self._find_server_by_slug(server_slug)
        await self._ensure_connected(server.uuid)
        await self._populate_server_info(server)
        await self._populate_resources(server)
        return f"""
"""


    @tool(internal=True)
    async def list_mcp_tools(self, server_slug: str, agent: AgentRef) -> str:
        """List the tools exposed by an MCP server, with their argument schemas.

        Reads the cached catalog fetched at startup; does not require a live
        connection to the server.

        Args:
            server_slug: The slug of the MCP server (as shown in the provider listing).

        Returns:
            str: A description of each available tool and its input schema.
        """
        server = self._find_server_by_slug(server_slug)
        if not server.resources_loaded:
            return (
                f"The catalog for MCP server '{server_slug}' could not be loaded "
                "at startup, so its tools are unknown."
            )
        tools = [r for r in server.resources.values() if isinstance(r, MCPToolResource)]
        if not tools:
            return f"MCP server '{server.name}' advertises no tools."

        parts = [f"Tools for MCP server '{server.name}':\n"]
        for mcp_tool in tools:
            parts.append(f"- {mcp_tool.tool_name}: {mcp_tool.description or '(no description)'}")
            if mcp_tool.input_schema:
                parts.append(f"    input schema: {json.dumps(mcp_tool.input_schema)}")
        return "\n".join(parts)

    @tool(internal=True)
    async def call_mcp_tool(
        self, server_slug: str, tool_name: str, arguments: dict, agent: AgentRef
    ) -> str:
        """Invoke a tool on an MCP server and return its result.

        Reuses the server's kept-open session, connecting on first use.

        Args:
            server_slug: The slug of the MCP server.
            tool_name: The tool to invoke.
            arguments: A mapping of argument names to values, matching the
                tool's input schema. Pass an empty object for tools that take
                no arguments.

        Returns:
            str: The tool's result content.
        """
        server = self._find_server_by_slug(server_slug)
        conn = await self._ensure_connected(server.uuid)
        result = await conn.run(lambda s: s.call_tool(tool_name, arguments or {}))
        text = self._flatten_content(result.content)
        if getattr(result, "isError", False):
            return f"MCP tool '{tool_name}' on '{server.name}' returned an error:\n{text}"
        return text or "(tool returned no content)"

    @tool(internal=True)
    async def read_mcp_resource(self, server_slug: str, uri: str, agent: AgentRef) -> str:
        """Read a resource (by URI) from an MCP server.

        Reuses the server's kept-open session, connecting on first use.

        Args:
            server_slug: The name of the MCP server.
            uri: The resource URI, as listed by the server.

        Returns:
            str: The resource contents.
        """
        server = self._find_server_by_slug(server_slug)
        conn = await self._ensure_connected(server.uuid)
        result = await conn.run(lambda s: s.read_resource(AnyUrl(uri)))
        return self._flatten_resource_contents(result.contents) or "(resource is empty)"


# ---------------------------------------------------------------------------
# OPEN QUESTIONS
#
# 1. Connection lifecycle. RESOLVED for now: connect+fetch+disconnect at
#    startup, then per-call ephemeral sessions (option b). This is simple and
#    correct but pays reconnect cost on every tool call and loses any
#    server-side session state between calls. Deferred: hold sessions open
#    across calls (option a/c). Doing so needs a long-lived owning task,
#    because the anyio cancel scopes inside the transport CMs must be entered
#    and exited on the *same* task — you cannot connect on one task and later
#    disconnect on another without hitting "cancel scope in a different task".
#    Also deferred: moving the blocking startup load to a background task.
#
# 2. Tool surfacing. Generic dispatch (call_mcp_tool) is the least invasive
#    fit for the existing static `tools` property. Registering each remote
#    tool as a first-class agent tool gives the agent better affordances but
#    needs dynamic registration + JSON-schema -> tool-signature translation,
#    and re-registration when a server's tool list changes.
#
# 3. Where the dataclasses live (here vs. types.py) and whether MCP prompts
#    should map onto Beaker's existing prompt/resource machinery at all.
#
# 4. Auth/secrets for HTTP servers (headers) and env for stdio servers —
#    where those come from and how they're kept out of config-in-repo.
# ---------------------------------------------------------------------------

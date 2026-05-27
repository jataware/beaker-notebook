"""Tests for tools defined on BeakerAgent (lib/agent.py)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from beaker_notebook.lib.agent import BeakerAgent
from beaker_notebook.lib.utils import normalize_notebook


def _agent_instance() -> BeakerAgent:
    return BeakerAgent.__new__(BeakerAgent)


def _nbstate_with_outputs() -> dict:
    """Notebook state fixture with mixed multimedia and text outputs."""
    return normalize_notebook({
        "cells": [
            {
                "cell_type": "code",
                "id": "cell-a",
                "source": "plot_and_print()",
                "metadata": {},
                "outputs": [
                    {
                        "output_type": "display_data",
                        "data": {
                            "text/plain": "<Figure>",
                            "image/png": "PNG_BASE64",
                        },
                        "metadata": {},
                    },
                    {
                        "output_type": "stream",
                        "name": "stdout",
                        "text": "hello\n",
                    },
                ],
            },
            {
                "cell_type": "code",
                "id": "cell-b",
                "source": "x = 1",
                "metadata": {},
                "outputs": [
                    {
                        "output_type": "execute_result",
                        "execution_count": 2,
                        "data": {"text/plain": "1"},
                        "metadata": {},
                    },
                ],
            },
        ],
        "metadata": {"kernelspec": {"name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    })


# --- ask_user --------------------------------------------------------------


async def test_ask_user_proxies_to_kernel_prompt_user():
    agent = _agent_instance()
    msg = MagicMock()
    prompt_user = AsyncMock(return_value="my reply")
    agent.context = SimpleNamespace(
        beaker_kernel=SimpleNamespace(prompt_user=prompt_user),
    )
    react_context = {"message": msg}

    result = await BeakerAgent.ask_user(
        agent,
        query="What is your name?",
        format=None,
        agent=MagicMock(),
        loop=MagicMock(),
        react_context=react_context,
    )

    assert result == "my reply"
    prompt_user.assert_awaited_once_with(
        "What is your name?", format=None, parent_message=msg,
    )


async def test_ask_user_passes_format():
    agent = _agent_instance()
    prompt_user = AsyncMock(return_value="ok")
    agent.context = SimpleNamespace(
        beaker_kernel=SimpleNamespace(prompt_user=prompt_user),
    )

    await BeakerAgent.ask_user(
        agent,
        query="continue?",
        format="workflow-confirmation",
        agent=MagicMock(),
        loop=MagicMock(),
        react_context={},
    )

    _, kwargs = prompt_user.call_args
    assert kwargs["format"] == "workflow-confirmation"
    assert kwargs["parent_message"] is None


# --- notebook_state (statetool) -------------------------------------------


async def test_notebook_state_renders_xml_via_notebook_state_to_xml():
    agent = _agent_instance()
    nbstate = _nbstate_with_outputs()
    subkernel = SimpleNamespace(
        KERNEL_NAME="python3",
        DISPLAY_NAME="Python 3",
        JUPYTER_LANGUAGE="python",
    )
    agent.context = SimpleNamespace(
        notebook_state=nbstate,
        subkernel=subkernel,
        slug="default",
        FULL_NAME="default.context",
        config={"context_info": {"k": "v"}},
        beaker_kernel=SimpleNamespace(session_id="sess-123"),
    )

    result = await BeakerAgent.notebook_state(agent)

    assert isinstance(result, str)
    # session id and kernelspec land in the rendered XML
    assert 'session-id="sess-123"' in result
    assert '"name": "python3"' in result
    assert '"display_name": "Python 3"' in result
    # context-info carries slug/name/config
    assert '"slug": "default"' in result
    assert '"name": "default.context"' in result
    # cell ids show up
    assert 'id="cell-a"' in result
    assert 'id="cell-b"' in result
    # ref is emitted only on the multimedia data record
    assert 'ref="cell-a:output:0:image/png"' in result
    # text/plain data records and stream outputs do NOT carry refs
    assert 'ref="cell-a:output:0:text/plain"' not in result
    assert "cell-a:output:1" not in result  # the stream output
    # parsed cleanly as XML
    import xml.etree.ElementTree as ET
    ET.fromstring(result)


async def test_notebook_state_escapes_session_id():
    agent = _agent_instance()
    agent.context = SimpleNamespace(
        notebook_state={"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5},
        subkernel=SimpleNamespace(KERNEL_NAME="python3", DISPLAY_NAME="Python 3", JUPYTER_LANGUAGE="python"),
        slug="s", FULL_NAME="n", config={"context_info": {}},
        beaker_kernel=SimpleNamespace(session_id='weird"id<>&'),
    )

    result = await BeakerAgent.notebook_state(agent)
    # raw value must not appear unescaped as an attribute
    assert 'session-id="weird"id<>&"' not in result
    import xml.etree.ElementTree as ET
    ET.fromstring(result)  # must still parse


# --- get_notebook_cell ----------------------------------------------------


async def test_get_notebook_cell_returns_formatted_cell():
    agent = _agent_instance()
    agent.context = SimpleNamespace(notebook_state=_nbstate_with_outputs())

    result = await BeakerAgent.get_notebook_cell(agent, "cell-a")

    assert isinstance(result, str)
    assert 'id="cell-a"' in result
    # exclude_media=True strips the image data record entirely
    assert "image/png" not in result
    assert "PNG_BASE64" not in result
    # text-side content is preserved
    assert "plot_and_print()" in result
    assert "&lt;Figure&gt;" in result  # text/plain content, xml-escaped


async def test_get_notebook_cell_rejects_non_string_id():
    agent = _agent_instance()
    agent.context = SimpleNamespace(notebook_state=_nbstate_with_outputs())

    with pytest.raises(ValueError, match="cell_id must be a string"):
        await BeakerAgent.get_notebook_cell(agent, 123)  # type: ignore[arg-type]


# --- get_notebook_multimedia_output ---------------------------------------


async def test_get_notebook_multimedia_output_returns_blocks_for_resolved_refs():
    from archytas.multimodal import MultiModalResponse
    agent = _agent_instance()
    agent.context = SimpleNamespace(notebook_state=_nbstate_with_outputs())

    blocks = await BeakerAgent.get_notebook_multimedia_output(
        agent, refs=["cell-a:output:0:image/png"],
    )

    assert isinstance(blocks, MultiModalResponse)
    assert blocks == MultiModalResponse([{
        "type": "image",
        "mime_type": "image/png",
        "base64": "PNG_BASE64",
    }])


async def test_get_notebook_multimedia_output_rejects_empty_refs():
    agent = _agent_instance()
    agent.context = SimpleNamespace(notebook_state=_nbstate_with_outputs())

    with pytest.raises(ValueError, match="must contain at least one ref"):
        await BeakerAgent.get_notebook_multimedia_output(agent, refs=[])


async def test_get_notebook_multimedia_output_raises_on_unresolved_ref():
    agent = _agent_instance()
    agent.context = SimpleNamespace(notebook_state=_nbstate_with_outputs())

    # missing mimetype suffix — exactly the failure mode the new docstring warns about
    with pytest.raises(ValueError) as exc_info:
        await BeakerAgent.get_notebook_multimedia_output(
            agent, refs=["cell-a:output:0"],
        )
    msg = str(exc_info.value)
    assert "cell-a:output:0" in msg
    # the valid ref is surfaced for self-correction
    assert "cell-a:output:0:image/png" in msg


async def test_get_notebook_multimedia_output_excludes_text_mimetypes():
    """Even though execute_result has a text/plain data record, it is not addressable
    via this tool — the error must list it as unresolved, not return it as a block."""
    agent = _agent_instance()
    agent.context = SimpleNamespace(notebook_state=_nbstate_with_outputs())

    with pytest.raises(ValueError) as exc_info:
        await BeakerAgent.get_notebook_multimedia_output(
            agent, refs=["cell-b:output:0:text/plain"],
        )
    # the only valid ref in the fixture is the image one; the text-only cell should
    # not contribute any entries to the available list
    msg = str(exc_info.value)
    assert "cell-b:output:0:text/plain" in msg  # listed as missing
    assert "cell-a:output:0:image/png" in msg   # the only available ref


async def test_get_notebook_multimedia_output_partial_failure_raises():
    """When some refs resolve and some don't, the call still raises rather than
    silently returning a partial result."""
    agent = _agent_instance()
    agent.context = SimpleNamespace(notebook_state=_nbstate_with_outputs())

    with pytest.raises(ValueError) as exc_info:
        await BeakerAgent.get_notebook_multimedia_output(
            agent,
            refs=["cell-a:output:0:image/png", "bogus-ref"],
        )
    assert "bogus-ref" in str(exc_info.value)


# --- get_multimedia_file_from_storage -------------------------------------


def _agent_with_kernel(jupyter_server: str = "http://jupyter.local/") -> BeakerAgent:
    agent = _agent_instance()
    agent.context = SimpleNamespace(
        beaker_kernel=SimpleNamespace(
            jupyter_server=jupyter_server,
            api_auth=MagicMock(return_value="auth-token"),
        ),
    )
    return agent


def _mock_response(status_code: int = 200, json_data: dict | None = None, text: str = "") -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json = MagicMock(return_value=json_data or {})
    response.text = text
    return response


async def test_get_multimedia_file_from_storage_returns_image_block():
    from archytas.multimodal import MultiModalResponse
    agent = _agent_with_kernel()
    response = _mock_response(json_data={
        "type": "file",
        "mimetype": "image/png",
        "content": "PNG_BASE64_DATA",
    })

    with patch("beaker_notebook.lib.agent.requests.get", return_value=response) as mock_get:
        result = await BeakerAgent.get_multimedia_file_from_storage(agent, "plots/scatter.png")

    assert isinstance(result, MultiModalResponse)
    assert result == MultiModalResponse([{
        "type": "image",
        "mime_type": "image/png",
        "base64": "PNG_BASE64_DATA",
    }])
    # path is fetched via the file manager contents API on the jupyter server
    url = mock_get.call_args.args[0]
    assert url == "http://jupyter.local/api/contents/plots/scatter.png"
    kwargs = mock_get.call_args.kwargs
    assert kwargs["params"] == {"content": "1", "format": "base64"}
    assert kwargs["headers"] == {"X-AUTH-BEAKER": "auth-token"}


async def test_get_multimedia_file_from_storage_strips_leading_slash_and_url_encodes():
    agent = _agent_with_kernel()
    response = _mock_response(json_data={
        "type": "file",
        "mimetype": "image/png",
        "content": "X",
    })

    with patch("beaker_notebook.lib.agent.requests.get", return_value=response) as mock_get:
        await BeakerAgent.get_multimedia_file_from_storage(agent, "/folder with space/a.png")

    url = mock_get.call_args.args[0]
    # leading slash stripped, spaces percent-encoded
    assert url == "http://jupyter.local/api/contents/folder%20with%20space/a.png"


async def test_get_multimedia_file_from_storage_strips_newlines_from_base64():
    from archytas.multimodal import MultiModalResponse
    agent = _agent_with_kernel()
    response = _mock_response(json_data={
        "type": "file",
        "mimetype": "image/jpeg",
        "content": "AAAA\nBBBB\nCCCC\n",
    })

    with patch("beaker_notebook.lib.agent.requests.get", return_value=response):
        result = await BeakerAgent.get_multimedia_file_from_storage(agent, "p.jpg")

    assert result == MultiModalResponse([{
        "type": "image",
        "mime_type": "image/jpeg",
        "base64": "AAAABBBBCCCC",
    }])


async def test_get_multimedia_file_from_storage_infers_mimetype_when_missing():
    agent = _agent_with_kernel()
    response = _mock_response(json_data={
        "type": "file",
        "mimetype": None,
        "content": "DATA",
    })

    from archytas.multimodal import MultiModalResponse
    with patch("beaker_notebook.lib.agent.requests.get", return_value=response):
        result = await BeakerAgent.get_multimedia_file_from_storage(agent, "clip.wav")

    assert result == MultiModalResponse([{
        "type": "audio",
        "mime_type": "audio/x-wav",
        "base64": "DATA",
    }])


async def test_get_multimedia_file_from_storage_rejects_empty_path():
    agent = _agent_with_kernel()
    with pytest.raises(ValueError, match="non-empty string"):
        await BeakerAgent.get_multimedia_file_from_storage(agent, "   ")


async def test_get_multimedia_file_from_storage_rejects_non_string_path():
    agent = _agent_with_kernel()
    with pytest.raises(ValueError, match="non-empty string"):
        await BeakerAgent.get_multimedia_file_from_storage(agent, 123)  # type: ignore[arg-type]


async def test_get_multimedia_file_from_storage_raises_on_404():
    agent = _agent_with_kernel()
    response = _mock_response(status_code=404, text="not found")

    with patch("beaker_notebook.lib.agent.requests.get", return_value=response):
        with pytest.raises(ValueError, match="File not found in user storage"):
            await BeakerAgent.get_multimedia_file_from_storage(agent, "missing.png")


async def test_get_multimedia_file_from_storage_raises_on_http_error():
    agent = _agent_with_kernel()
    response = _mock_response(status_code=500, text="boom")

    with patch("beaker_notebook.lib.agent.requests.get", return_value=response):
        with pytest.raises(ValueError, match="status 500"):
            await BeakerAgent.get_multimedia_file_from_storage(agent, "p.png")


async def test_get_multimedia_file_from_storage_rejects_directory():
    agent = _agent_with_kernel()
    response = _mock_response(json_data={"type": "directory", "content": None})

    with patch("beaker_notebook.lib.agent.requests.get", return_value=response):
        with pytest.raises(ValueError, match="not a file"):
            await BeakerAgent.get_multimedia_file_from_storage(agent, "folder")


async def test_get_multimedia_file_from_storage_rejects_non_multimedia_mimetype():
    agent = _agent_with_kernel()
    response = _mock_response(json_data={
        "type": "file",
        "mimetype": "text/plain",
        "content": "aGVsbG8=",
    })

    with patch("beaker_notebook.lib.agent.requests.get", return_value=response):
        with pytest.raises(ValueError, match="not a supported multimedia type"):
            await BeakerAgent.get_multimedia_file_from_storage(agent, "notes.txt")


async def test_get_multimedia_file_from_storage_rejects_unknown_mimetype():
    """When the server returns no mimetype and mimetypes can't guess one, reject."""
    agent = _agent_with_kernel()
    response = _mock_response(json_data={
        "type": "file",
        "mimetype": None,
        "content": "DATA",
    })

    with patch("beaker_notebook.lib.agent.requests.get", return_value=response):
        with pytest.raises(ValueError, match="not a supported multimedia type"):
            await BeakerAgent.get_multimedia_file_from_storage(agent, "file.unknown-ext-xyz")


async def test_get_multimedia_file_from_storage_raises_when_content_missing():
    agent = _agent_with_kernel()
    response = _mock_response(json_data={
        "type": "file",
        "mimetype": "image/png",
        "content": None,
    })

    with patch("beaker_notebook.lib.agent.requests.get", return_value=response):
        with pytest.raises(ValueError, match="did not return base64 content"):
            await BeakerAgent.get_multimedia_file_from_storage(agent, "p.png")

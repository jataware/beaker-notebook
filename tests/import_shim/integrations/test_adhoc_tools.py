"""Tests for the @tool methods on AdhocIntegrationProvider.

These exercise the tool-method logic directly with mocked dependencies.
The provider's __init__ wires up adhoc_api and reads disk; we sidestep it
with __new__ and inject the few fields each tool actually touches.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from beaker_kernel.lib.integrations.adhoc import AdhocIntegrationProvider


def _provider(specifications=None, adhoc_api=None) -> AdhocIntegrationProvider:
    p = AdhocIntegrationProvider.__new__(AdhocIntegrationProvider)
    p.specifications = specifications or []
    p.adhoc_api = adhoc_api
    return p


# --- add_example -----------------------------------------------------------


async def test_add_example_unknown_integration():
    provider = _provider(specifications=[])
    result = await AdhocIntegrationProvider.add_example(
        provider, integration="missing", query="q", code="c", notes="n",
    )
    assert "Failed to look up" in result


async def test_add_example_calls_add_resource():
    spec = SimpleNamespace(slug="my-int", uuid="u-1")
    provider = _provider(specifications=[spec])
    provider.add_resource = MagicMock(return_value=None)

    result = await AdhocIntegrationProvider.add_example(
        provider, integration="my-int", query="q", code="c", notes="n",
    )

    provider.add_resource.assert_called_once_with(
        "u-1", resource_type="example", query="q", code="c", notes="n",
    )
    assert "added to my-int" in result


async def test_add_example_failed_add_resource():
    spec = SimpleNamespace(slug="my-int", uuid="u-1")
    provider = _provider(specifications=[spec])
    provider.add_resource = MagicMock(side_effect=RuntimeError("disk full"))

    result = await AdhocIntegrationProvider.add_example(
        provider, integration="my-int", query="q", code="c", notes="n",
    )
    assert "Add resource tool failed" in result


# --- draft_integration_code -----------------------------------------------


async def test_draft_integration_code_returns_drafted_code():
    adhoc = MagicMock()
    adhoc.use_api.return_value = "import x"
    provider = _provider(adhoc_api=adhoc)

    result = await AdhocIntegrationProvider.draft_integration_code(
        provider, integration="my-int", goal="do thing",
        agent=MagicMock(), loop=MagicMock(), react_context={},
    )
    adhoc.use_api.assert_called_once_with("my-int", "do thing")
    assert "import x" in result


async def test_draft_integration_code_handles_exception():
    adhoc = MagicMock()
    adhoc.use_api.side_effect = RuntimeError("nope")
    provider = _provider(adhoc_api=adhoc)

    result = await AdhocIntegrationProvider.draft_integration_code(
        provider, integration="my-int", goal="x",
        agent=MagicMock(), loop=MagicMock(), react_context={},
    )
    assert "error occurred" in result.lower()
    assert "nope" in result


async def test_draft_integration_code_no_api_key_returns_helpful_message():
    """When adhoc_api is None, the error path emits the GEMINI_API_KEY hint."""
    provider = _provider(adhoc_api=None)
    # Calling .use_api on None will raise AttributeError, which is caught.
    result = await AdhocIntegrationProvider.draft_integration_code(
        provider, integration="x", goal="y",
        agent=MagicMock(), loop=MagicMock(), react_context={},
    )
    assert "GEMINI_API_KEY" in result


# --- consult_integration_docs ---------------------------------------------


async def test_consult_integration_docs_returns_results():
    adhoc = MagicMock()
    adhoc.ask_api.return_value = "Endpoints: /foo /bar"
    provider = _provider(adhoc_api=adhoc)

    result = await AdhocIntegrationProvider.consult_integration_docs(
        provider, integration="my-int", query="what endpoints?",
        agent=MagicMock(), loop=MagicMock(), react_context={},
    )
    adhoc.ask_api.assert_called_once_with("my-int", "what endpoints?")
    assert "/foo" in result


async def test_consult_integration_docs_handles_exception():
    adhoc = MagicMock()
    adhoc.ask_api.side_effect = ValueError("bad")
    provider = _provider(adhoc_api=adhoc)

    result = await AdhocIntegrationProvider.consult_integration_docs(
        provider, integration="my-int", query="?",
        agent=MagicMock(), loop=MagicMock(), react_context={},
    )
    assert "error occurred" in result.lower()
    assert "bad" in result


async def test_consult_integration_docs_no_api_key():
    provider = _provider(adhoc_api=None)
    result = await AdhocIntegrationProvider.consult_integration_docs(
        provider, integration="x", query="y",
        agent=MagicMock(), loop=MagicMock(), react_context={},
    )
    assert "GEMINI_API_KEY" in result

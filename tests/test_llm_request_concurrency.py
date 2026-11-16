from types import SimpleNamespace

import pytest

from beaker_notebook.kernel import BeakerKernel


@pytest.mark.asyncio
async def test_overlapping_llm_request_does_not_mutate_active_context():
    context = SimpleNamespace(current_llm_query="first", session_attachments=["existing"])
    kernel = SimpleNamespace(
        context=context,
        _llm_request_active=True,
        get_session_attachments=lambda ids: [],
    )
    message = SimpleNamespace(content={"request": "second"}, metadata={})

    with pytest.raises(RuntimeError, match="already running"):
        await BeakerKernel.llm_request.__wrapped__(kernel, message)

    assert context.current_llm_query == "first"
    assert context.session_attachments == ["existing"]

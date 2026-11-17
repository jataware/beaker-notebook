import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from beaker_notebook.kernel import BeakerKernel


class PendingAgent:
    def __init__(self):
        self.pending_message = None

    def queue_message(self, message):
        assert self.pending_message is None
        self.pending_message = message

    def cancel_pending_message(self):
        pending, self.pending_message = self.pending_message, None
        return pending


@pytest.fixture
def kernel():
    kernel = BeakerKernel.__new__(BeakerKernel)
    kernel.context = SimpleNamespace(agent=PendingAgent())
    kernel._llm_request_active = True
    kernel._pending_llm_revision = 0
    kernel.send_response = Mock()
    return kernel


async def request(kernel, operation, **content):
    message = SimpleNamespace(content={"operation": operation, **content}, header={"msg_id": "request"})
    return await BeakerKernel.llm_pending_request.__wrapped__(kernel, message)


@pytest.mark.asyncio
async def test_queue_edit_cancel_and_revision(kernel):
    queued = await request(kernel, "queue", id="one", text="original")
    assert queued == {"state": "pending", "id": "one", "text": "original", "revision": 1}
    assert kernel.context.agent.pending_message.content == "[User message received during the current task]\noriginal"
    occupied = await request(kernel, "queue", id="two", text="another")
    assert occupied["state"] == "occupied"
    edited = await request(kernel, "edit", id="one", text="changed")
    assert edited == {"state": "pending", "id": "one", "text": "changed", "revision": 2}
    assert (await request(kernel, "cancel", id="old"))["state"] == "not_pending"
    assert (await request(kernel, "cancel", id="one")) == {"state": "cancelled", "id": "one", "revision": 3}
    assert await request(kernel, "status") == {"state": "empty", "revision": 3}


@pytest.mark.asyncio
async def test_attachments_are_rejected_only_while_agent_is_active(kernel):
    assert await request(kernel, "queue", id="one", text="with file", has_attachments=True) == {
        "state": "attachments_not_supported",
    }
    assert kernel.context.agent.pending_message is None
    kernel._llm_request_active = False
    assert await request(kernel, "queue", id="one", text="with file", has_attachments=True) == {
        "state": "inactive",
    }


@pytest.mark.asyncio
async def test_validation_does_not_discard_original(kernel):
    await request(kernel, "queue", id="one", text="original")
    with pytest.raises(ValueError):
        await request(kernel, "edit", id="one", text=" ")
    assert (await request(kernel, "status"))["text"] == "original"


@pytest.mark.asyncio
async def test_inactive_and_deferred(kernel):
    kernel._llm_request_active = False
    assert await request(kernel, "queue", id="one", text="original") == {"state": "inactive"}
    kernel._llm_request_active = True
    await request(kernel, "queue", id="one", text="original")
    kernel._llm_request_active = False
    assert (await request(kernel, "status"))["state"] == "deferred"


@pytest.mark.asyncio
async def test_interjection_notification_is_attributed_to_active_request(kernel):
    agent = kernel.context.agent
    started = asyncio.Event()
    resume = asyncio.Event()

    async def run_agent(query, react_context):
        started.set()
        await resume.wait()
        agent.on_message_interjected(agent.cancel_pending_message())
        return "answer"

    agent.react_async = run_agent
    kernel.context.ensure_system_preamble_fresh = AsyncMock()
    kernel.get_session_attachments = Mock(return_value=[])
    kernel.running_actions = {}
    kernel.debug = Mock()
    kernel.handle_react_step = Mock()
    kernel.handle_tool_call_update = Mock()
    kernel.send_set_chat_history = AsyncMock()
    kernel._llm_request_active = False
    message = SimpleNamespace(content={"request": "first"}, metadata={}, header={"msg_id": "first"})
    task = asyncio.create_task(BeakerKernel.llm_request.__wrapped__(kernel, message))
    await started.wait()
    await request(kernel, "queue", id="one", text="follow up")
    resume.set()
    await task
    updates = [call for call in kernel.send_response.call_args_list if call.args[1] == "llm_pending_update"]
    assert [call.args[2]["state"] for call in updates] == ["pending", "sent"]
    assert updates[-1].kwargs["parent_header"] == message.header
    assert agent.on_message_interjected is None


@pytest.mark.asyncio
async def test_message_arriving_during_cleanup_is_deferred(kernel):
    agent = kernel.context.agent
    agent.react_async = AsyncMock(return_value="answer")
    kernel.context.ensure_system_preamble_fresh = AsyncMock()
    kernel.get_session_attachments = Mock(return_value=[])
    kernel.running_actions = {}
    kernel.debug = Mock()
    kernel.handle_react_step = Mock()
    kernel.handle_tool_call_update = Mock()
    cleanup_started = asyncio.Event()
    finish_cleanup = asyncio.Event()

    async def send_history(header):
        cleanup_started.set()
        await finish_cleanup.wait()

    kernel.send_set_chat_history = send_history
    kernel._llm_request_active = False
    message = SimpleNamespace(content={"request": "first"}, metadata={}, header={"msg_id": "first"})
    task = asyncio.create_task(BeakerKernel.llm_request.__wrapped__(kernel, message))
    await cleanup_started.wait()
    assert (await request(kernel, "queue", id="one", text="follow up"))["state"] == "pending"
    finish_cleanup.set()
    await task
    assert (await request(kernel, "status"))["state"] == "deferred"
    updates = [call.args[2] for call in kernel.send_response.call_args_list if call.args[1] == "llm_pending_update"]
    assert [update["state"] for update in updates] == ["pending", "deferred"]


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_failure_restores_pending_message(kernel, cancel):
    agent = kernel.context.agent
    started = asyncio.Event()
    release = asyncio.Event()

    async def run_agent(query, react_context):
        started.set()
        await release.wait()
        raise RuntimeError("failed")

    agent.react_async = run_agent
    kernel.context.ensure_system_preamble_fresh = AsyncMock()
    kernel.get_session_attachments = Mock(return_value=[])
    kernel.running_actions = {}
    kernel.debug = Mock()
    kernel.handle_react_step = Mock()
    kernel.handle_tool_call_update = Mock()
    kernel._llm_request_active = False
    message = SimpleNamespace(content={"request": "first"}, metadata={}, header={"msg_id": "first"})
    task = asyncio.create_task(BeakerKernel.llm_request.__wrapped__(kernel, message))
    await started.wait()
    await request(kernel, "queue", id="one", text="follow up")
    if cancel:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        release.set()
        with pytest.raises(RuntimeError, match="failed"):
            await task
    assert agent.pending_message is None
    updates = [call.args[2] for call in kernel.send_response.call_args_list
               if len(call.args) > 1 and call.args[1] == "llm_pending_update"]
    assert updates[-1] == {"state": "restored", "id": "one", "text": "follow up", "revision": 2}


@pytest.mark.asyncio
async def test_deferred_message_is_claimed_as_next_turn(kernel):
    agent = kernel.context.agent
    await request(kernel, "queue", id="one", text="follow up")
    kernel._llm_request_active = False
    agent.react_async = AsyncMock(return_value="answer")
    kernel.context.ensure_system_preamble_fresh = AsyncMock()
    kernel.get_session_attachments = Mock(return_value=[])
    kernel.running_actions = {}
    kernel.debug = Mock()
    kernel.handle_react_step = Mock()
    kernel.handle_tool_call_update = Mock()
    kernel.send_set_chat_history = AsyncMock()
    message = SimpleNamespace(
        content={"request": "follow up", "pending_id": "one"},
        metadata={}, header={"msg_id": "next"},
    )
    await BeakerKernel.llm_request.__wrapped__(kernel, message)
    assert agent.pending_message is None
    assert agent.react_async.await_args.args[0] == "[User message received during the current task]\nfollow up"
    updates = [call.args[2] for call in kernel.send_response.call_args_list if call.args[1] == "llm_pending_update"]
    assert [update["state"] for update in updates] == ["pending", "sent"]

"""Tests for tools defined on BeakerSubkernel (lib/subkernel.py).

Covers:
- kernel_state (statetool): payload normalization, budget application
- describe_variables: missing template, missing names, happy path
- run_code: minimal sanity (invokes execute with provided code)
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from beaker_notebook.lib.subkernel import BeakerSubkernel


class _ConcreteSubkernel(BeakerSubkernel):
    DISPLAY_NAME = "Test"
    SLUG = "test"
    JUPYTER_LANGUAGE = "test"

    @classmethod
    def parse_subkernel_return(cls, execution_result):
        return execution_result


def _subkernel_instance() -> BeakerSubkernel:
    """Build a minimal subkernel without going through Jupyter wiring."""
    sk = _ConcreteSubkernel.__new__(_ConcreteSubkernel)
    sk.context = SimpleNamespace(templates={}, evaluate=AsyncMock(), get_code=MagicMock())
    return sk


# --- kernel_state ----------------------------------------------------------


async def test_kernel_state_returns_empty_when_no_state():
    sk = _subkernel_instance()
    sk._get_state = AsyncMock(return_value=None)
    result = await BeakerSubkernel.kernel_state(sk)
    assert result == ""


async def test_kernel_state_renders_dict_payload():
    sk = _subkernel_instance()
    sk._get_state = AsyncMock(return_value={
        "local_names": {"x": "int(42)"},
        "variables": {"x": {"type": "int", "sample": "42", "truncated": False}},
    })
    sk._kernel_state_budget = lambda: 1000
    result = await BeakerSubkernel.kernel_state(sk)
    assert "## Kernel state" in result
    assert "`x`: int(42)" in result
    assert "int" in result


async def test_kernel_state_handles_legacy_non_dict():
    sk = _subkernel_instance()
    sk._get_state = AsyncMock(return_value=["legacy", "list"])
    result = await BeakerSubkernel.kernel_state(sk)
    assert "## Kernel state" in result
    assert "legacy" in result


async def test_kernel_state_applies_sample_budget():
    sk = _subkernel_instance()
    sk._get_state = AsyncMock(return_value={
        "local_names": {"big": "DataFrame"},
        "variables": {"big": {"type": "DataFrame", "sample": "x" * 5000, "truncated": False}},
    })
    sk._kernel_state_budget = lambda: 100
    result = await BeakerSubkernel.kernel_state(sk)
    # Sample should be truncated; original 5000 chars must NOT be present in full
    assert "x" * 5000 not in result


# --- describe_variables ----------------------------------------------------


async def test_describe_variables_no_names():
    sk = _subkernel_instance()
    result = await BeakerSubkernel.describe_variables(sk, names=[], agent=MagicMock())
    assert "no names" in result.lower()


async def test_describe_variables_no_template_returns_hint():
    sk = _subkernel_instance()
    sk.context.templates = {}  # no describe_variables template
    result = await BeakerSubkernel.describe_variables(sk, names=["foo"], agent=MagicMock())
    assert "does not provide" in result


async def test_describe_variables_returns_payload():
    sk = _subkernel_instance()
    sk.context.templates = {"describe_variables": "<template>"}
    sk.context.get_code = MagicMock(return_value="rendered_code")
    sk.context.evaluate = AsyncMock(return_value={"return": {
        "variables": {"foo": {"type": "int", "sample": "42"}},
        "missing": ["bar"],
    }})
    sk.reflectors = {}
    sk._describe_variables_budget = lambda: 1000

    result = await BeakerSubkernel.describe_variables(
        sk, names=["foo", "bar"], agent=MagicMock(),
    )
    assert "## Variable descriptions" in result
    assert "foo" in result
    assert "Names not found" in result
    assert "`bar`" in result


async def test_describe_variables_missing_only():
    sk = _subkernel_instance()
    sk.context.templates = {"describe_variables": "<template>"}
    sk.context.get_code = MagicMock(return_value="rendered")
    sk.context.evaluate = AsyncMock(return_value={"return": {"variables": {}, "missing": ["x"]}})
    sk.reflectors = {}
    sk._describe_variables_budget = lambda: 1000

    result = await BeakerSubkernel.describe_variables(sk, names=["x"], agent=MagicMock())
    assert "Names not found" in result
    assert "## Variable descriptions" in result


# --- run_code (minimal) ----------------------------------------------------
# run_code is heavy (touches the kernel proxy, message bus, and execution
# tasks). We exercise only the boundary: that the tool calls
# context.execute() with the agent-supplied code. Anything deeper belongs
# to integration tests against a real kernel.

async def test_run_code_invokes_context_execute():
    """Smoke test: run_code calls context.execute with the supplied code,
    awaits the resulting task, and serializes the execution report."""
    import asyncio

    sk = _subkernel_instance()
    code = "print('hello')"

    exec_request = SimpleNamespace(
        json_field_names=["msg_id", "header"],
        msg_id="m1",
        header={"msg_id": "m1"},
    )
    exec_context_dict = {
        "id": "m1", "done": True, "error": None, "command": code,
        "stdout_list": ["hello"], "stderr_list": [], "display_data_list": [], "return": None,
    }

    loop = asyncio.get_event_loop()
    fake_task = loop.create_future()
    fake_task.set_result(exec_context_dict)
    # Attach the attribute run_code reads off the task object.
    fake_task.execute_request_msg = exec_request

    subkernel_obj = SimpleNamespace(SLUG="test")
    context = SimpleNamespace(
        subkernel=subkernel_obj,
        execute=MagicMock(return_value=fake_task),
        send_response=MagicMock(),
        preview=AsyncMock(return_value={}),
        kernel_state=AsyncMock(return_value=""),
    )
    agent_ref = SimpleNamespace(context=context)

    msg = SimpleNamespace(header={"msg_id": "m1"}, identities=[])
    react_context = {"message": msg}

    # CheckpointableBeakerSubkernel branch must be skipped — our fake subkernel
    # is not an instance of it, so the isinstance check fails naturally.
    result = await BeakerSubkernel.run_code(
        sk, code=code, agent=agent_ref, loop=MagicMock(), react_context=react_context,
    )

    context.execute.assert_called_once()
    call_args, call_kwargs = context.execute.call_args
    assert call_args[0] == code
    assert "Execution Report Complete" in result
    assert "hello" in result

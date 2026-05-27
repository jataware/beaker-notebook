"""Tests for tools defined on DefaultAgent."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from beaker_kernel.contexts.default.agent import DefaultAgent
from beaker_kernel.lib.utils import ExecutionError


def _agent_instance() -> DefaultAgent:
    """Return a DefaultAgent shell that bypasses ReActAgent.__init__."""
    return DefaultAgent.__new__(DefaultAgent)


# --- tell_a_joke -----------------------------------------------------------


async def test_tell_a_joke_returns_evaluated_joke():
    agent = _agent_instance()
    agent_ref = SimpleNamespace(context=SimpleNamespace(evaluate=AsyncMock(return_value={"return": "Why did the chicken cross the road?"})))

    result = await DefaultAgent.tell_a_joke(
        agent, topic="any", agent=agent_ref, loop=MagicMock(),
    )
    assert "chicken" in result
    agent_ref.context.evaluate.assert_awaited_once()


async def test_tell_a_joke_falls_back_on_execution_error():
    agent = _agent_instance()
    agent_ref = SimpleNamespace(
        context=SimpleNamespace(evaluate=AsyncMock(side_effect=ExecutionError("E", "boom", []))),
    )

    result = await DefaultAgent.tell_a_joke(
        agent, topic="any", agent=agent_ref, loop=MagicMock(),
    )
    assert "elephant" in result.lower()

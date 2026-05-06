"""Tests for tools on WorkflowRegistry (lib/workflow.py)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from beaker_kernel.lib.workflow import (
    Workflow,
    WorkflowRegistry,
    WorkflowStage,
    WorkflowStep,
    WorkflowStageProgress,
    workflow_condition,
)


def _make_workflow(title: str = "Build Pipeline") -> Workflow:
    return Workflow(
        title=title,
        agent_description="agent desc",
        human_description="human desc",
        example_prompt="example",
        stages=[
            WorkflowStage(
                name="stage_one",
                description="first stage",
                steps=[WorkflowStep(prompt="do thing")],
            )
        ],
    )


def _make_agent_ref(workflows: dict, attached: Workflow | None = None):
    state = {
        "workflow_id": "wf-uuid",
        "progress": {"stage_one": None},
        "final_response": "",
    }
    context = SimpleNamespace(
        workflows=workflows,
        current_workflow_state=state,
        attached_workflow=attached,
        attach_workflow=MagicMock(),
        send_response=MagicMock(),
    )
    return SimpleNamespace(context=context), state, context


# --- attach_workflow -------------------------------------------------------


async def test_attach_workflow_no_workflows():
    registry = WorkflowRegistry()
    agent_ref, _, _ = _make_agent_ref(workflows={})
    result = await WorkflowRegistry.attach_workflow(registry, "anything", agent=agent_ref)
    assert "No workflows" in result


async def test_attach_workflow_unknown_title():
    wf = _make_workflow()
    registry = WorkflowRegistry({"u1": wf})
    agent_ref, _, _ = _make_agent_ref(workflows={"u1": wf})
    result = await WorkflowRegistry.attach_workflow(registry, "no-such-thing", agent=agent_ref)
    assert "Failed to find" in result


async def test_attach_workflow_success_calls_context_attach():
    wf = _make_workflow("Build Pipeline")
    registry = WorkflowRegistry({"u1": wf})
    agent_ref, _, ctx = _make_agent_ref(workflows={"u1": wf})

    result = await WorkflowRegistry.attach_workflow(registry, "Build Pipeline", agent=agent_ref)

    assert "Successfully" in result
    ctx.attach_workflow.assert_called_once_with("u1")
    ctx.send_response.assert_called_once()


# --- update_workflow_stage -------------------------------------------------


async def test_update_workflow_stage_invalid_state():
    registry = WorkflowRegistry()
    agent_ref, _, _ = _make_agent_ref(workflows={})
    result = await WorkflowRegistry.update_workflow_stage(
        registry, stage_name="stage_one", state="bogus", results="", agent=agent_ref,
    )
    assert "State must be one of" in result


async def test_update_workflow_stage_unknown_stage():
    registry = WorkflowRegistry()
    agent_ref, _, _ = _make_agent_ref(workflows={})
    result = await WorkflowRegistry.update_workflow_stage(
        registry, stage_name="missing", state="finished", results="r", agent=agent_ref,
    )
    assert "Stage name not found" in result


async def test_update_workflow_stage_writes_progress():
    registry = WorkflowRegistry()
    agent_ref, state, ctx = _make_agent_ref(workflows={})
    result = await WorkflowRegistry.update_workflow_stage(
        registry, stage_name="stage_one", state="finished", results="done", agent=agent_ref,
    )
    assert "Successfully" in result
    progress = state["progress"]["stage_one"]
    assert progress["state"] == "finished"
    assert progress["results_markdown"] == "done"
    ctx.send_response.assert_called_once()


# --- update_workflow_output ------------------------------------------------


async def test_update_workflow_output_sets_final_response():
    registry = WorkflowRegistry()
    agent_ref, state, ctx = _make_agent_ref(workflows={})
    result = await WorkflowRegistry.update_workflow_output(
        registry, results="# Final report", agent=agent_ref,
    )
    assert "Successfully" in result
    assert state["final_response"] == "# Final report"
    ctx.send_response.assert_called_once()


# --- attached_workflow_state (statetool) -----------------------------------


def test_attached_workflow_state_when_attached():
    wf = _make_workflow()
    registry = WorkflowRegistry({"u1": wf})
    agent_ref, _, ctx = _make_agent_ref(workflows={"u1": wf}, attached=wf)
    result = WorkflowRegistry.attached_workflow_state(registry, agent=agent_ref)
    assert "<title>Build Pipeline</title>" in result


def test_attached_workflow_state_when_none():
    registry = WorkflowRegistry()
    agent_ref, _, _ = _make_agent_ref(workflows={}, attached=None)
    result = WorkflowRegistry.attached_workflow_state(registry, agent=agent_ref)
    assert result == "No context currently attached."


def test_workflow_condition_reflects_attachment():
    wf = _make_workflow()
    agent_ref, _, _ = _make_agent_ref(workflows={"u1": wf}, attached=wf)
    assert workflow_condition(agent_ref) is True

    agent_ref_unattached, _, _ = _make_agent_ref(workflows={"u1": wf}, attached=None)
    assert workflow_condition(agent_ref_unattached) is False

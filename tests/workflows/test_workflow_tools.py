"""Tests for tools on WorkflowRegistry (lib/workflow.py)."""

import json
from functools import partial
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from beaker_notebook.lib.workflow import (
    Workflow,
    WorkflowRegistry,
    WorkflowStage,
    WorkflowStep,
    WorkflowState,
    WorkflowStageProgress,
    create_available_workflows_prompt,
    workflow_condition,
)


def _make_context(workflows, state, attached, *kwargs) -> SimpleNamespace:
    from beaker_notebook.lib.context import BeakerContext

    ns = SimpleNamespace(
        workflows=workflows,
        current_workflow_state=state,
        attached_workflow=attached,
        attach_workflow=MagicMock(),
        send_response=MagicMock(),
        send_workflow_state=None,
    )
    ns.send_workflow_state = partial(BeakerContext.send_workflow_state, ns)

    return ns


def _make_workflow(
    title: str = "Build Pipeline",
    id: str = None,
    agent_instructions: str | None = None,
    hidden: bool = False,
) -> Workflow:
    return Workflow(
        title=title,
        id=id,
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
        agent_instructions=agent_instructions,
        hidden=hidden,
    )


def _make_agent_ref(
    workflows: dict,
    attached: Workflow | None = None,
    progress: dict | None = None,
):
    if progress is None:
        progress = {"stage_one": None}
    state = WorkflowState(
        workflow_id="wf-uuid",
        progress=progress,
        final_response="",
    )
    context = _make_context(workflows, state, attached)
    return SimpleNamespace(context=context), state, context


def _make_multistage_workflow(title: str = "Weather Report") -> Workflow:
    return Workflow(
        title=title,
        agent_description="agent desc",
        human_description="human desc",
        example_prompt="example",
        stages=[
            WorkflowStage(
                name="Collect METAR data",
                description="first stage",
                steps=[WorkflowStep(prompt="fetch the data")],
            ),
            WorkflowStage(
                name="Assess flight conditions",
                description="second stage",
                steps=[
                    WorkflowStep(prompt="evaluate ceilings"),
                    WorkflowStep(prompt="evaluate visibility"),
                ],
            ),
            WorkflowStage(
                name="Summarize",
                description="third stage",
                steps=[WorkflowStep(prompt="write summary")],
            ),
        ],
    )


def _multistage_agent_ref(attached: Workflow):
    progress = {stage.name: None for stage in attached.stages}
    return _make_agent_ref(
        workflows={"u1": attached}, attached=attached, progress=progress,
    )


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


async def test_attach_workflow_success_calls_context_attach_no_id():
    wf = _make_workflow("Build Pipeline")
    workflow_id = wf.id
    registry = WorkflowRegistry({workflow_id: wf})
    agent_ref, _, ctx = _make_agent_ref(workflows=registry)

    result = await WorkflowRegistry.attach_workflow.run(args={"workflow_id": workflow_id, "agent": agent_ref}, tool_context={"agent": agent_ref}, self_ref=registry)

    assert isinstance(workflow_id, str)
    assert len(workflow_id) > 0
    assert "Successfully" in result
    assert workflow_id in result
    ctx.attach_workflow.assert_called_once_with(wf)
    ctx.send_response.assert_called_once()


async def test_attach_workflow_success_calls_context_attach_with_id():
    workflow_id = "build_pipeline_id"
    wf = _make_workflow("Build Pipeline", id=workflow_id)
    registry = WorkflowRegistry({workflow_id: wf})
    agent_ref, _, ctx = _make_agent_ref(workflows=registry)

    result = await WorkflowRegistry.attach_workflow.run(args={"workflow_id": workflow_id, "agent": agent_ref}, tool_context={"agent": agent_ref}, self_ref=registry)

    assert "Successfully" in result
    assert workflow_id in result
    ctx.attach_workflow.assert_called_once_with(wf)
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
    wf = _make_workflow()
    registry = WorkflowRegistry()
    agent_ref, state, ctx = _make_agent_ref(workflows={"u1": wf}, attached=wf)
    result = await WorkflowRegistry.update_workflow_stage(
        registry, stage_name="stage_one", state="finished", results="done", agent=agent_ref,
    )
    progress = state.progress["stage_one"]
    assert progress.state == "finished"
    assert progress.results_markdown == "done"
    ctx.send_response.assert_called_once()
    # single-stage workflow finished -> completion message
    assert "Stage 1 of 1" in result
    assert "complete" in result.lower()
    assert "update_workflow_output" in result


# --- #191: slug matching + clean error message -----------------------------


async def test_update_workflow_stage_unknown_stage_message_has_no_dict_keys():
    wf = _make_multistage_workflow()
    registry = WorkflowRegistry()
    agent_ref, _, _ = _multistage_agent_ref(wf)
    result = await WorkflowRegistry.update_workflow_stage(
        registry, stage_name="nonexistent", state="finished", results="r", agent=agent_ref,
    )
    assert "Stage name not found" in result
    assert "dict_keys" not in result
    assert "Collect METAR data" in result
    assert "Assess flight conditions" in result


async def test_update_workflow_stage_slug_match_resolves_variant():
    wf = _make_multistage_workflow()
    registry = WorkflowRegistry()
    agent_ref, state, _ = _multistage_agent_ref(wf)
    # differs in case/punctuation/whitespace from "Collect METAR data"
    result = await WorkflowRegistry.update_workflow_stage(
        registry,
        stage_name=" Collect METAR-data ",
        state="finished",
        results="data collected",
        agent=agent_ref,
    )
    assert "Stage name not found" not in result
    # canonical key was the one mutated
    assert state.progress["Collect METAR data"].state == "finished"


async def test_update_workflow_stage_slug_match_resolves_extra_spaces():
    wf = _make_multistage_workflow()
    registry = WorkflowRegistry()
    agent_ref, state, _ = _multistage_agent_ref(wf)
    # differs in case/punctuation/whitespace from "Collect METAR data"
    result = await WorkflowRegistry.update_workflow_stage(
        registry,
        stage_name="Collect    METAR-data",
        state="finished",
        results="data collected",
        agent=agent_ref,
    )
    assert "Stage name not found" not in result
    # canonical key was the one mutated
    assert state.progress["Collect METAR data"].state == "finished"



# --- #192: invariant enforcement -------------------------------------------


async def test_update_workflow_stage_finished_blank_results_rejected():
    wf = _make_multistage_workflow()
    registry = WorkflowRegistry()
    agent_ref, state, ctx = _multistage_agent_ref(wf)
    result = await WorkflowRegistry.update_workflow_stage(
        registry,
        stage_name="Collect METAR data",
        state="finished",
        results="   ",
        agent=agent_ref,
    )
    assert "not modified" in result
    assert state.progress["Collect METAR data"] is None
    ctx.send_response.assert_not_called()


async def test_update_workflow_stage_in_progress_nonblank_results_rejected():
    wf = _make_multistage_workflow()
    registry = WorkflowRegistry()
    agent_ref, state, ctx = _multistage_agent_ref(wf)
    result = await WorkflowRegistry.update_workflow_stage(
        registry,
        stage_name="Collect METAR data",
        state="in_progress",
        results="some results",
        agent=agent_ref,
    )
    assert "not modified" in result
    assert state.progress["Collect METAR data"] is None
    ctx.send_response.assert_not_called()


async def test_update_workflow_stage_out_of_order_finish_warns_but_records():
    wf = _make_multistage_workflow()
    registry = WorkflowRegistry()
    agent_ref, state, _ = _multistage_agent_ref(wf)
    # finish the 2nd stage while the 1st is still unstarted
    result = await WorkflowRegistry.update_workflow_stage(
        registry,
        stage_name="Assess flight conditions",
        state="finished",
        results="conditions ok",
        agent=agent_ref,
    )
    assert state.progress["Assess flight conditions"].state == "finished"
    assert "Warning" in result
    assert "Collect METAR data" in result


# --- #190: cursor / re-grounding in the return value -----------------------


async def test_update_workflow_stage_finished_nonfinal_names_next_stage_and_steps():
    wf = _make_multistage_workflow()
    registry = WorkflowRegistry()
    agent_ref, _, _ = _multistage_agent_ref(wf)
    result = await WorkflowRegistry.update_workflow_stage(
        registry,
        stage_name="Collect METAR data",
        state="finished",
        results="data",
        agent=agent_ref,
    )
    assert "Stage 1 of 3" in result
    assert 'Next stage: "Assess flight conditions"' in result
    assert "evaluate ceilings" in result
    assert "evaluate visibility" in result


async def test_update_workflow_stage_finished_final_states_complete():
    wf = _make_multistage_workflow()
    registry = WorkflowRegistry()
    agent_ref, _, _ = _multistage_agent_ref(wf)
    await WorkflowRegistry.update_workflow_stage(
        registry,
        stage_name="Collect METAR data",
        state="finished",
        results="stage1",
        agent=agent_ref,
    )
    await WorkflowRegistry.update_workflow_stage(
        registry,
        stage_name="Assess flight conditions",
        state="finished",
        results="stage2",
        agent=agent_ref,
    )
    result = await WorkflowRegistry.update_workflow_stage(
        registry,
        stage_name="Summarize",
        state="finished",
        results="summary",
        agent=agent_ref,
    )
    assert "Stage 3 of 3" in result
    assert "complete" in result.lower()
    assert "update_workflow_output" in result
    assert "warning" not in result.lower()


async def test_update_workflow_stage_finished_final_states_complete_with_skipped():
    wf = _make_multistage_workflow()
    registry = WorkflowRegistry()
    agent_ref, _, _ = _multistage_agent_ref(wf)
    result = await WorkflowRegistry.update_workflow_stage(
        registry,
        stage_name="Summarize",
        state="finished",
        results="summary",
        agent=agent_ref,
    )
    assert "Stage 3 of 3" in result
    assert "complete" in result.lower()
    assert "update_workflow_output" in result
    assert "warning" in result.lower()


async def test_update_workflow_stage_in_progress_confirms_position():
    wf = _make_multistage_workflow()
    registry = WorkflowRegistry()
    agent_ref, _, _ = _multistage_agent_ref(wf)
    result = await WorkflowRegistry.update_workflow_stage(
        registry,
        stage_name="Assess flight conditions",
        state="in_progress",
        results="",
        agent=agent_ref,
    )
    assert "Stage 2 of 3" in result
    assert "in progress" in result.lower()


# --- update_workflow_output ------------------------------------------------


async def test_update_workflow_output_sets_final_response():
    registry = WorkflowRegistry()
    agent_ref, state, ctx = _make_agent_ref(workflows={})
    result = await WorkflowRegistry.update_workflow_output(
        registry, results="# Final report", agent=agent_ref,
    )
    assert "Successfully" in result
    assert state.final_response == "# Final report"
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


# --- agent_instructions field ----------------------------------------------

# A sentinel that is unlikely to appear incidentally in any other prompt text,
# so assertions about its presence/absence are unambiguous.
AGENT_INSTRUCTIONS = "SECRET-AGENT-GUIDANCE: prefer pandas over polars for this task."


def test_from_yaml_parses_agent_instructions():
    wf = Workflow.from_yaml({
        "title": "T",
        "agent_description": "a",
        "human_description": "h",
        "example_prompt": "e",
        "stages": [],
        "agent_instructions": AGENT_INSTRUCTIONS,
    })
    assert wf.agent_instructions == AGENT_INSTRUCTIONS


def test_from_yaml_agent_instructions_defaults_to_none():
    wf = Workflow.from_yaml({
        "title": "T",
        "agent_description": "a",
        "human_description": "h",
        "example_prompt": "e",
        "stages": [],
    })
    assert wf.agent_instructions is None


def test_to_prompt_includes_agent_instructions_when_set():
    wf = _make_workflow(agent_instructions=AGENT_INSTRUCTIONS)
    prompt = wf.to_prompt()
    assert "<agent-instructions>" in prompt
    assert "</agent-instructions>" in prompt
    assert AGENT_INSTRUCTIONS in prompt


def test_to_prompt_omits_agent_instructions_when_unset():
    wf = _make_workflow(agent_instructions=None)
    prompt = wf.to_prompt()
    assert "<agent-instructions>" not in prompt
    assert AGENT_INSTRUCTIONS not in prompt


# --- agent_instructions are NOT in the system prompt -----------------------
#
# The system prompt lists the available workflows via
# create_available_workflows_prompt / WorkflowRegistry.system_preamble. The
# agent_instructions must not leak there; they should only become visible once
# a workflow is actually selected (attached) and rendered via to_prompt().


def test_available_workflows_prompt_excludes_agent_instructions():
    wf = _make_workflow(agent_instructions=AGENT_INSTRUCTIONS)
    prompt = create_available_workflows_prompt([wf])
    assert AGENT_INSTRUCTIONS not in prompt
    assert "<agent-instructions>" not in prompt
    # the synopsis-level fields are still present
    assert wf.title in prompt
    assert wf.agent_description in prompt


async def test_system_preamble_excludes_agent_instructions():
    wf = _make_workflow(agent_instructions=AGENT_INSTRUCTIONS)
    registry = WorkflowRegistry({"u1": wf})
    preamble = await registry.system_preamble()
    assert preamble is not None
    assert AGENT_INSTRUCTIONS not in preamble
    assert "<agent-instructions>" not in preamble


# --- agent_instructions ARE visible once the workflow is selected ----------


def test_attached_workflow_state_exposes_agent_instructions():
    wf = _make_workflow(agent_instructions=AGENT_INSTRUCTIONS)
    registry = WorkflowRegistry({"u1": wf})
    agent_ref, _, _ = _make_agent_ref(workflows={"u1": wf}, attached=wf)
    result = WorkflowRegistry.attached_workflow_state(registry, agent=agent_ref)
    assert "<agent-instructions>" in result
    assert AGENT_INSTRUCTIONS in result


def test_agent_instructions_only_appear_after_selection():
    """End-to-end: instructions are absent from the system preamble but present
    once the workflow is attached and its state is rendered."""
    wf = _make_workflow(agent_instructions=AGENT_INSTRUCTIONS)
    registry = WorkflowRegistry({"u1": wf})

    preamble = create_available_workflows_prompt(list(registry.values()))
    assert AGENT_INSTRUCTIONS not in preamble

    agent_ref, _, _ = _make_agent_ref(workflows={"u1": wf}, attached=wf)
    attached_state = WorkflowRegistry.attached_workflow_state(registry, agent=agent_ref)
    assert AGENT_INSTRUCTIONS in attached_state


# --- #196: WorkflowState must survive the wire as a dataclass --------------
#
# WorkflowState / WorkflowStageProgress moved from TypedDict to dataclass. The
# emit sites hand the state to send_response, whose real serialization is a bare
# json.dumps with no dataclass fallback. These tests use a send_response that
# reproduces that serialization, so they FAIL (TypeError) until the state is
# converted to a plain dict (e.g. asdict / to_dict) at each emit site, and they
# also pin the wire shape — including the removal of the dead `code_cell_id`.


async def test_update_workflow_stage_emits_wire_serializable_state():
    wf = _make_workflow()
    registry = WorkflowRegistry()
    agent_ref, state, context = _make_agent_ref(
        workflows={"u1": wf}, attached=wf,
    )
    await WorkflowRegistry.update_workflow_stage(
        registry, stage_name="stage_one", state="finished", results="done", agent=agent_ref,
    )
    assert context.send_response.call_count == 1
    _, msg_type, payload = context.send_response.call_args.args
    assert msg_type == "update_workflow_state"
    assert payload["workflow_id"] == "wf-uuid"
    assert payload["final_response"] == ""
    stage = payload["progress"]["stage_one"]
    assert stage["state"] == "finished"
    assert stage["results_markdown"] == "done"
    # Dead field removed (#196 item 1): it must not reappear on the wire.
    assert "code_cell_id" not in stage


async def test_update_workflow_output_emits_wire_serializable_state():
    registry = WorkflowRegistry()
    agent_ref, state, context = _make_agent_ref(workflows={})
    await WorkflowRegistry.update_workflow_output(
        registry, results="# Final report", agent=agent_ref,
    )
    assert context.send_response.call_count == 1
    _, msg_type, payload = context.send_response.call_args.args
    assert msg_type == "update_workflow_state"
    assert payload["final_response"] == "# Final report"


async def test_attach_workflow_emits_wire_serializable_state():
    wf = _make_workflow("Build Pipeline")
    workflow_id = wf.id
    registry = WorkflowRegistry({workflow_id: wf})
    agent_ref, state, context = _make_agent_ref(workflows=registry)

    await WorkflowRegistry.attach_workflow.run(
        args={"workflow_id": workflow_id, "agent": agent_ref},
        tool_context={"agent": agent_ref},
        self_ref=registry,
    )
    assert context.send_response.call_count == 1
    _, msg_type, payload = context.send_response.call_args.args
    assert msg_type == "update_workflow_state"
    assert payload["workflow_id"] == "wf-uuid"
    assert "progress" in payload
    assert "final_response" in payload


# --- #196 item 2: hidden workflows are not surfaced to the agent -----------
#
# `hidden: true` means "not surfaced proactively." For the agent that means the
# workflow is omitted from the synopsis (create_available_workflows_prompt /
# system_preamble); it stays attachable by id. (The UI half of this -- the
# picker -- is enforced in WorkflowSelectDialog.vue.)


def test_hidden_workflow_excluded_from_synopsis():
    visible = _make_workflow("Visible Flow")
    hidden = _make_workflow("Hidden Flow", hidden=True)
    prompt = create_available_workflows_prompt([visible, hidden])
    assert "Visible Flow" in prompt
    assert visible.id in prompt
    assert "Hidden Flow" not in prompt
    assert hidden.id not in prompt


async def test_hidden_workflow_excluded_from_system_preamble():
    visible = _make_workflow("Visible Flow")
    hidden = _make_workflow("Hidden Flow", hidden=True)
    registry = WorkflowRegistry({visible.id: visible, hidden.id: hidden})
    preamble = await registry.system_preamble()
    assert preamble is not None
    assert "Visible Flow" in preamble
    assert "Hidden Flow" not in preamble


async def test_hidden_workflow_still_attachable_by_id():
    """Hidden only suppresses proactive surfacing; explicit attach still works."""
    hidden = _make_workflow("Hidden Flow", hidden=True)
    registry = WorkflowRegistry({hidden.id: hidden})
    agent_ref, _, ctx = _make_agent_ref(workflows=registry)

    result = await WorkflowRegistry.attach_workflow.run(
        args={"workflow_id": hidden.id, "agent": agent_ref},
        tool_context={"agent": agent_ref},
        self_ref=registry,
    )
    assert "Successfully" in result
    ctx.attach_workflow.assert_called_once_with(hidden)

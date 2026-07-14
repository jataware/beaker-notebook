from archytas.tool_utils import tool, statetool, AgentRef
from collections.abc import Mapping
from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING, Iterator, Literal, Optional, Any

from beaker_notebook.lib.utils import slugify

if TYPE_CHECKING:
    from .context import BeakerContext

WORKFLOW_PREAMBLE_PROMPT="""
## Workflows

```xml
<workflows>
A workflow is a named, multi-stage procedure for solving an end-to-end problem.
Each workflow has STAGES; each stage has ordered STEPS. At most one workflow
is ACTIVE at a time.

## Executing the active workflow

For each stage, in order:
1. Perform every step in sequence. Never substitute assumed or example data
   for missing data — stop and ask the user.
2. Call `ask_user` (format: `workflow-confirmation`) to confirm before continuing.
3. Resolve the response:
   - "continue" or `ask_user` times out: call `update_workflow_stage` with
     state="finished" and the stage's results in markdown. Emit each stage's
     results exactly once, here — do not re-emit earlier stages' results. If the
     user confirmed, call `update_workflow_stage` for the next stage with
     state="in_progress" and begin its steps. If `ask_user` timed out, stop
     and wait for the user to message to resume.
   - "cancel": stop. The workflow may be resumed later.
   - anything else: treat as a normal user request; it takes precedence over
     advancing the workflow. If handling it changes a stage's results, redo
     the affected work and call `update_workflow_stage` again with the new
     values. Only call `update_workflow_output` again if the workflow has
     already completed — otherwise the final assembly step below picks up the
     corrected results.

When every stage is finished, assemble the final output once: call
`update_workflow_output` with the complete report for all stages, formatted per
the active workflow's `<workflow-result-formatting-instructions>`. Do this a
single time, at the end. The per-stage results you already emitted via
`update_workflow_stage` are retained and shown to the user as the workflow runs,
so there is no need to re-emit cumulative output between stages.

## Selecting a workflow

- If the user's request matches an available workflow, tell them so and use
  `ask_user` to confirm before attaching it via `attach_workflow`. Skip this
  if the matching workflow is already attached.

## Workflow output

When embedding images in workflow output, use HTML so they render at a
readable size:
`<img src="/files/my_viz.png" alt="..." style="width:85%; display:block; margin:auto;" />`
Files saved relative to the agent working directory are served under /files/
(e.g. `./my_viz.png` → `/files/my_viz.png`).

## Available workflows

<workflows-list>
{workflow_synopsis}
</workflows-list>
</workflows>
```
"""

@dataclass(kw_only=True)
class WorkflowStep:
    prompt: str
    metadata: Optional[dict[str, Any]] = field(default_factory=lambda: {})

    @staticmethod
    def from_yaml(source: str | dict[str, Any]) -> "WorkflowStep":
        match source:
            case str():
                return WorkflowStep(prompt=source, metadata={})
            case dict():
                return WorkflowStep(prompt=source["prompt"], metadata=source.get("metadata", {}))


@dataclass(kw_only=True)
class WorkflowStage:
    name: str
    steps: list[WorkflowStep] = field(metadata={"terse-action": "truncate"})
    metadata: Optional[dict[str, Any]] = field(default_factory=lambda: {})
    # human readable string describing the stage
    description: Optional[list[str]]

    @staticmethod
    def from_yaml(source: dict[str, Any]) -> "WorkflowStage":
        return WorkflowStage(
            name=source["name"],
            description=source.get("description", None),
            steps=[WorkflowStep.from_yaml(step) for step in source["steps"]],
            metadata=source.get("metadata", {})
        )


@dataclass(kw_only=True)
class Workflow:
    id: Optional[str] = field(default=None)
    title: str
    agent_description: str = field(metadata={"terse-action": "truncate"})
    human_description: str
    example_prompt: str
    stages: list[WorkflowStage]

    # When true, the workflow is not surfaced proactively: it is excluded from
    # both the agent's workflow synopsis (see create_available_workflows_prompt
    # below) and the UI picker (filtered in beaker-vue's WorkflowSelectDialog.vue,
    # since the full set is still shipped to the client as a by-id lookup table).
    # It remains attachable by explicit id -- e.g. as a context default
    # (is_context_default) or via a programmatic attach.
    hidden: Optional[bool] = field(default=False)
    is_context_default: Optional[bool] = field(default=False)
    category: Optional[str] = field(default=None)
    metadata: Optional[dict[str, Any]] = field(default_factory=lambda: {})
    output_prompt: Optional[str] = field(default=None, metadata={"terse-action": "truncate"})
    agent_instructions: Optional[str] = field(default=None)

    def __post_init__(self):
        # Ensure workflows have stable IDs, creating one from the title if not included.
        self.title = self.title.strip()
        if not self.id:
            self.id = slugify(self.title)

        # Normalize hidden to a real bool: from_yaml passes None when the key is
        # absent, and downstream filters test it directly.
        self.hidden = bool(self.hidden)

        # Reject duplicate stage names. Progress is keyed by stage name and
        # `update_workflow_stage` matches the agent's input via
        # slugify(..., collapse=True); names that are equal -- or merely
        # slug-equal (differ only in case/punctuation/whitespace) -- would
        # collapse into a single progress slot. Detect collisions on the slug so
        # those variants are caught too, and fail load with a clear message
        # (discovery turns this into a per-file skip).
        seen: dict[str, str] = {}
        for stage in self.stages:
            key = slugify(stage.name, collapse=True)
            if key in seen:
                raise ValueError(
                    f"Workflow {self.title!r} has a duplicate stage name "
                    f"{stage.name!r} (collides with {seen[key]!r}); stage names "
                    "must be unique."
                )
            seen[key] = stage.name

    @staticmethod
    def from_yaml(source: dict[str, Any]) -> "Workflow":
        stages = [WorkflowStage.from_yaml(stage) for stage in source.get("stages", [])]
        return Workflow(
            title=source["title"],
            agent_description=source["agent_description"],
            human_description=source["human_description"],
            example_prompt=source["example_prompt"],
            stages=stages,

            id=source.get("id", None),
            hidden=source.get("hidden", None),
            category=source.get("category", None),
            is_context_default=source.get("is_context_default", False),
            metadata=source.get("metadata", {}),
            output_prompt=source.get("output_prompt", None),
            agent_instructions=source.get("agent_instructions", None),
        )

    # text representation of the prompt itself, fed directly into the agent.
    def to_prompt(self) -> str:
        formatted_stages = []
        for stage in self.stages:
            stage_parts = [f'<stage name="{stage.name!r}">']
            if stage.description:
                desc = "\n".join(stage.description) if isinstance(stage.description, list) else stage.description
                stage_parts.append(f"<description>{desc}</description>")
            stage_parts.append("<steps>")
            stage_parts.extend(f"<step>{step.prompt}</step>" for step in stage.steps)
            stage_parts.append("</steps>")
            stage_parts.append("</stage>")
            formatted_stages.append("\n".join(stage_parts))

        output_prompt = self.output_prompt or "Format the result as markdown."
        prompt_parts = [
            f"<title>{self.title}</title>",
            f"<id>{self.id}</id>",
            "<stages>",
            *formatted_stages,
            "</stages>",
            "",
            "<workflow-result-formatting-instructions>",
            output_prompt,
            "",
            "Cite each finding back to the stage and step it came from, so the "
            "reader can trace any conclusion to the work that produced it.",
            "</workflow-result-formatting-instructions>",
            "",
        ]
        if self.agent_instructions:
            prompt_parts.extend([
                "<agent-instructions>",
                self.agent_instructions,
                "</agent-instructions>",
                "",
            ])

        return "\n".join(prompt_parts)


@dataclass(kw_only=True)
class WorkflowStageProgress:
    state: Literal['in_progress', 'finished']
    results_markdown: str


@dataclass(kw_only=True)
class WorkflowState:
    workflow_id: str
    progress: dict[str, WorkflowStageProgress | None]
    final_response: str

    @classmethod
    def from_workflow(cls, workflow: Workflow) -> "WorkflowState":
        return cls(
            workflow_id=workflow.id,
            progress={
                stage.name: None
                for stage in workflow.stages
            },
            final_response=""
        )


def create_available_workflows_prompt(
    workflows: list[Workflow],
) -> str:
    """
    Create a fully rendered prompt for the context based on a list of workflows and which,
    if any, of them is active.

    Hidden workflows are omitted from the synopsis so the agent does not surface
    them proactively; they remain attachable by explicit id.
    """
    workflow_synopsis = "\n\n".join([
        f"""<workflow>
    <title>{workflow.title}</title>
    <id>{workflow.id}</id>
    <description>{workflow.agent_description}</description>
</workflow>"""
        for workflow in workflows
        if not workflow.hidden
    ])

    return WORKFLOW_PREAMBLE_PROMPT.format(
        workflow_synopsis=workflow_synopsis,
    )


def workflow_condition(agent: AgentRef) -> bool:
    context: BeakerContext = agent.context
    return bool(context.attached_workflow)

class WorkflowRegistry(Mapping[str, Workflow]):
    """Mapping container of workflows keyed by id, with a system_preamble
    contribution that lists the available workflows for the agent.

    Mirrors the role of IntegrationProviderRegistry: holds a collection and
    contributes a single composed prompt block summarizing it.
    """

    def __init__(self, workflows: Optional[dict[str, Workflow]] = None):
        self._workflows: dict[str, Workflow] = dict(workflows) if workflows else {}

    def __getitem__(self, workflow_id: str) -> Workflow:
        return self._workflows[workflow_id]

    def __iter__(self) -> Iterator[str]:
        return iter(self._workflows)

    def __len__(self) -> int:
        return len(self._workflows)

    def __bool__(self) -> bool:
        return bool(self._workflows)

    @property
    def default(self) -> Workflow|None:
        for workflow in self.values():
            if workflow.is_context_default:
                return workflow
        return None

    async def system_preamble(self) -> Optional[str]:
        if not self._workflows:
            return None
        return create_available_workflows_prompt(list(self._workflows.values()))

    @tool(internal=True)
    async def attach_workflow(self, workflow_id: str|None, agent: AgentRef):
        """
        Chooses a relevant workflow to the user's request and attaches it to the context.

        If the user wants to detach a workflow or remove it, that is equivalent to attaching "none."

        Use this tool when the user asks to activate, enable, switch to, or attach a workflow.

        If they describe what they want to do, choose the most relevant workflow based on their query.

        Args:
            workflow_id (str|None): The id of an available workflow that you wish to attach, or None to detach the workflow.

        Returns:
            str: A summary of what was done
        """
        try:
            if len(self) == 0:
                return "No workflows in registry."
        except Exception as e:
            return f"Failed to get workflows on context. {e}"
        if workflow_id is None:
            workflow = None
        else:
            workflow = self.get(workflow_id, None)
            if workflow is None:
                return f"Failed to find workflow with id `{workflow_id}`. Existing workflows: `{(list(self.keys()))!r}`: invalid tool input."

        agent.context.attach_workflow(workflow)
        agent.context.send_workflow_state()
        return f'Successfully set the attached workflow to "{workflow.title}" ({workflow.id}).'

    @tool(internal=True)
    async def update_workflow_stage(self, stage_name: str, state: str, results: str, agent: AgentRef):
        """
        Updates the information about a workflow stage.

        This must be used directly after finishing each stage of a workflow,
        and at the start of a new stage.

        You may additionally use this if the user requests redoing a stage after providing additional information,
        such as: "Try that again, but with..." or "That didn't quite work, please fix it"
        that would impact the result of a stage of the workflow that has already completed.
        After following the user's request, ensure to provide the new results when updating the stage to be
        "finished" again.

        Args:
            stage_name (str): The name of the stage to mark as completed to the user.
                            This is matched leniently (case/punctuation/whitespace
                            insensitive) against the workflow's stage names.
            state (str): State will always either one of 'in_progress' or 'finished'.
                        If finished, results must not be blank.
                        If the stage is now in progress, results should be blank.
            results (str): The final response of the operation, formatted in markdown.
                        Format this in markdown if it is not already.
                        This argument must be an empty string if state is 'in_progress'.

        Returns:
            str: Information about the operation.
        """
        if state != 'in_progress' and state != 'finished':
            return "State must be one of `in_progress` or `finished`."

        # Resolve the agent's input to the canonical stored stage key via slugify on both sides.
        progress = agent.context.current_workflow_state.progress
        resolved_key = None
        desired = slugify(stage_name, collapse=True)
        for key in progress:
            if slugify(key, collapse=True) == desired:
                resolved_key = key
                break
        if resolved_key is None:
            stage_list = ", ".join(progress.keys())
            return f"Stage name not found. Must be one of: {stage_list}"

        results_blank = not results.strip()
        if state == 'finished' and results_blank:
            return (
                f"Stage '{resolved_key}' was not modified. When marking a stage "
                "'finished', you must supply the stage's results in markdown."
            )
        if state == 'in_progress' and not results_blank:
            return (
                f"Stage '{resolved_key}' was not modified. When marking a stage "
                "'in_progress', results must be blank."
            )

        # Collect skipped stages (earlier stages that have not yet been started) so we can warn the agent.
        skipped_stages: list[str] = []
        if state == 'finished':
            for key, value in progress.items():
                if key == resolved_key:
                    break
                if value is None:
                    skipped_stages.append(key)

        progress[resolved_key] = WorkflowStageProgress(
            state=state,
            results_markdown=results,
        )

        agent.context.send_workflow_state()

        return self._build_stage_response(agent, resolved_key, state, skipped_stages)

    def _build_stage_response(
        self,
        agent: AgentRef,
        resolved_key: str,
        state: str,
        skipped_stages: list[str],
    ) -> str:
        """Build the instructive return string for `update_workflow_stage`.

        Re-grounds the agent at every transition: its position (`N of M`), and,
        when finishing a non-final stage, the next stage's name and steps.
        """
        progress_keys = list(agent.context.current_workflow_state.progress.keys())
        total = len(progress_keys)
        index = progress_keys.index(resolved_key)  # zero-based
        position = f"Stage {index + 1} of {total}"

        next_key: Optional[str] = (
            progress_keys[index + 1] if index + 1 < total else None
        )

        workflow = agent.context.attached_workflow
        stages_by_name: dict[str, WorkflowStage] = {}
        if workflow is not None:
            stages_by_name = {stage.name: stage for stage in workflow.stages}

        lines: list[str] = []
        if state == 'in_progress':
            lines.append(f'{position} ("{resolved_key}") is now in progress.')
        else:
            lines.append(f'{position} ("{resolved_key}") marked finished.')
            if next_key is None:
                lines.append(
                    "The workflow is now complete. Call `update_workflow_output` "
                    "once with the complete report for all stages, formatted per the "
                    "workflow's `<workflow-result-formatting-instructions>`."
                )
            else:
                next_position = f"Stage {index + 2} of {total}"
                lines.append(f'Next stage: "{next_key}" ({next_position}) — steps:')
                next_stage = stages_by_name.get(next_key)
                if next_stage is not None and next_stage.steps:
                    for i, step in enumerate(next_stage.steps, start=1):
                        lines.append(f"  {i}. {step.prompt}")

        if skipped_stages:
            skipped_list = ", ".join(f'"{name}"' for name in skipped_stages)
            lines.append(
                f"Warning: the following earlier stage(s) are still unstarted: "
                f"{skipped_list}. If this was intentional (e.g. redoing work), "
                "you may continue; otherwise make sure no stages were skipped."
            )

        return "\n".join(lines)

    @tool(internal=True)
    async def update_workflow_output(self, results: str, agent: AgentRef):
        """
        Updates the overall output of the workflow.

        Call this tool once, after the final stage of the workflow finishes, to
        assemble the complete report. Call it again only if a change made after the
        workflow has already completed alters the final output. Do not call it
        between stages — per-stage results are emitted via `update_workflow_stage`
        and shown to the user as the workflow runs.

        The final output of the workflow must be formatted according to the
        `<workflow-result-formatting-instructions></workflow-result-formatting-instructions>`
        block of the active workflow.

        Args:
            results (str): The results of the entire workflow, all stages included, given
                        the state of the notebook and user operations as well -
                        which should be formatted according to the
                        `<workflow-result-formatting-instructions></workflow-result-formatting-instructions>` block of the active workflow.

        Returns:
            str: Information about the operation.
        """
        agent.context.current_workflow_state.final_response = results
        agent.context.send_workflow_state()
        return "Successfully set workflow output."


    @statetool(condition=workflow_condition)
    def attached_workflow_state(self, agent: AgentRef) -> str:
        """
        Provides the full state of the currently attached workflow.

        Returns:
            str: The state as xml
        """
        context: BeakerContext = agent.context
        if context.attached_workflow:
            return context.attached_workflow.to_prompt()
        else:
            return "No context currently attached."

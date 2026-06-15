from archytas.tool_utils import tool, statetool, AgentRef
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterator, Literal, Optional, Any, TypedDict

from beaker_notebook.lib.utils import slugify

if TYPE_CHECKING:
    from .context import BeakerContext

WORKFLOW_PREAMBLE_PROMPT="""
<workflows>
A workflow is a named, multi-stage procedure for solving an end-to-end problem.
Each workflow has STAGES; each stage has ordered STEPS. At most one workflow
is ACTIVE at a time.

## Executing the active workflow

For each stage, in order:
1. Perform every step in sequence. Never substitute assumed or example data
   for missing data — stop and ask the user.
2. Call `update_workflow_output` with the cumulative results so far, formatted
   per the active workflow's `<workflow-result-formatting-instructions>`.
3. Call `ask_user` (format: `workflow-confirmation`) to confirm before continuing.
4. Resolve the response:
   - "continue" or `ask_user` times out: call `update_workflow_stage` with
     state="finished" and the stage's results in markdown. If the user
     confirmed, call `update_workflow_stage` for the next stage with
     state="in_progress" and begin its steps. If `ask_user` timed out, stop
     and wait for the user to message to resume.
   - "cancel": stop. The workflow may be resumed later.
   - anything else: treat as a normal user request; it takes precedence over
     advancing the workflow. If handling it changes a stage's results, redo
     the affected work and call `update_workflow_stage` and
     `update_workflow_output` again with the new values.

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
    title: str
    agent_description: str = field(metadata={"terse-action": "truncate"})
    human_description: str
    example_prompt: str
    stages: list[WorkflowStage]

    hidden: Optional[bool] = field(default=False)
    is_context_default: Optional[bool] = field(default=False)
    category: Optional[str] = field(default=None)
    metadata: Optional[dict[str, Any]] = field(default_factory=lambda: {})
    output_prompt: Optional[str] = field(default=None, metadata={"terse-action": "truncate"})
    agent_instructions: Optional[str] = field(default=None)

    @staticmethod
    def from_yaml(source: dict[str, Any]) -> "Workflow":
        stages = [WorkflowStage.from_yaml(stage) for stage in source.get("stages", [])]
        return Workflow(
            title=source["title"],
            agent_description=source["agent_description"],
            human_description=source["human_description"],
            example_prompt=source["example_prompt"],
            stages=stages,

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
            stage_parts = [f"<stage name={stage.name!r}>"]
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


class WorkflowStageProgress(TypedDict):
    state: Literal['in_progress', 'finished']
    code_cell_id: str
    results_markdown: str


class WorkflowState(TypedDict):
    workflow_id: str
    progress: dict[str, WorkflowStageProgress | None]
    final_response: str

    @classmethod
    def from_workflow(cls, workflow_id: str, workflow: Workflow) -> "WorkflowState": # type: ignore
        return cls(
            workflow_id=workflow_id,
            progress={
                stage.name: None
                for stage in workflow.stages
            },
            final_response=""
        )


def create_available_workflows_prompt(
    workflows: list[Workflow],
    attached_workflow: Optional[Workflow] = None
) -> str:
    """
    Create a fully rendered prompt for the context based on a list of workflows and which,
    if any, of them is active.
    """
    workflow_synopsis = "\n\n".join([
        f"""<workflow>
    <title>{workflow.title}</title>
    <description>{workflow.agent_description}</description>
</workflow>"""
        for workflow in workflows
    ])

    return WORKFLOW_PREAMBLE_PROMPT.format(
        workflow_synopsis=workflow_synopsis,
    )


def workflow_condition(agent: AgentRef) -> bool:
    context: BeakerContext = agent.context
    return bool(context.attached_workflow)

class WorkflowRegistry(Mapping):
    """Mapping container of workflows keyed by UUID, with a system_preamble
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

    async def system_preamble(self) -> Optional[str]:
        if not self._workflows:
            return None
        return create_available_workflows_prompt(list(self._workflows.values()))

    @tool(internal=True)
    async def attach_workflow(self, workflow_title: str, agent: AgentRef):
        """
        Chooses a relevant workflow to the user's request and attaches it to the context.

        If the user wants to detach a workflow or remove it, that is equivalent to attaching "none."

        Use this tool when the user asks to activate, enable, switch to, or attach a workflow.

        If they describe what they want to do, choose the most relevant workflow based on their query.

        Args:
            workflow_title (str): The title of the workflow that you have access to, most relevant to their query.
                            This is "none" if the user wants to detach, remove, or unset the workflow.

        Returns:
            str: A summary of what was done
        """
        try:
            if len(agent.context.workflows) == 0:
                return "No workflows attached to context."
        except Exception as e:
            return f"Failed to get workflows on context. {e}"
        desired = slugify(workflow_title)
        titles = {
            slugify(workflow.title): uuid
            for uuid, workflow in agent.context.workflows.items()
        }
        if desired not in titles:
            return f"Failed to find `{desired}` in `{titles}`: invalid tool input."
        agent.context.attach_workflow(titles[desired])
        agent.context.send_response("iopub", "update_workflow_state", agent.context.current_workflow_state)
        return f"Successfully set the attached workflow to {workflow_title}."

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
                            IMPORTANT: This must be the exact name of the stage.
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
        if stage_name not in agent.context.current_workflow_state["progress"]:
            return f"Stage name not found. Must be one of: {agent.context.current_workflow_state['progress'].keys()}"
        agent.context.current_workflow_state["progress"][stage_name] = WorkflowStageProgress(
                code_cell_id='',
                state=state,
                results_markdown=results,
            )

        agent.context.send_response("iopub", "update_workflow_state", agent.context.current_workflow_state)
        return "Successfully marked stage."

    @tool(internal=True)
    async def update_workflow_output(self, results: str, agent: AgentRef):
        """
        Updates the overall output of the workflow.

        This tool must be called whenever a workflow stage completes, or whenever
        redoing a task would impact the "final output" of a workflow.

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
        agent.context.current_workflow_state["final_response"] = results
        agent.context.send_response("iopub", "update_workflow_state", agent.context.current_workflow_state)
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

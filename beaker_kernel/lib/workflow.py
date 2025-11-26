from dataclasses import dataclass, field
from typing import Literal, Optional, Any, TypedDict

WORKFLOW_PREAMBLE_PROMPT="""

<workflows>

# Workflows

- You will be given a few preselected workflows and processes to work through.
- A workflow is a commonly grouped set of tasks to solve an end-to-end problem.
- ONE workflow will be ACTIVE and currently ready for use.
  - You may replace the ACTIVE workflow if the user requests a different workflow, through the `attach_workflow` tool.
- Workflows are divided into STAGES that contain STEPS.

IMPORTANT: To execute a workflow, you will do each step in order. Upon finishing the last step, the STAGE is COMPLETE.

- CRITICAL: when a STAGE is COMPLETE, do all three of the following tasks in order, start to finish:
    1) use the "update_workflow_stage" tool and you must show the results of each STAGE to the user
    2) use the "update_workflow_output" to show the in-progress results to the user according to the `<workflow-result-formatting-instructions>` block of the active workflow.
    3) ask the user to confirm to continue, after you have called "update_workflow_output"
        - The response to `ask_user` will be "continue", "cancel", or something else -- such as a similar investigation or retrying a step.
        - Proceed if they choose to continue.
        - Stop the workflow if they choose to cancel. It may be resumed later.
        - Doing what else the user request takes precedence over the workflow if they request something else.
- The correct workflow pattern is: Complete stage → call update_workflow_stage → call update_workflow_output → call ask_user for confirmation → repeat

- CRITICAL: you MUST ask_user at each stage being completed.

- CRITICAL: after the user confirms to start the next STAGE, use the "update_workflow_stage" tool to communicate that the stage is in progress.
- CRITICAL: do not ever use assumed or example data if data is not available; stop and inform the user and ask how to proceed.

- CRITICAL: when new important information is gathered from the user, such as retrying a task, or from completing a workflow stage, you must use the "update_workflow_output" tool.

- IMPORTANT: When using `ask_user` in a workflow, use the `workflow_confirmation` format.

- When a user asks for something that aligns with a given workflow, you will communicate that it is within your skillset
    - Next, use the `ask_user` tool to ask them if this workflow looks correct and if they would like to start it.
- When starting a workflow, use the `display_workflow_panel` tool

- CRITICAL: you MUST provide clear citations for all findings and conclusions that you make. In particular, when generating workflow reports, be sure to include citations and also to enumerate your assumptions if you make any.

- NOTE: if the correct workflow that you want to attach is already attached, you do not need to attach it again.

- IMPORTANT: if you restart or redo a stage, make sure to `update_workflow_output` with the new results.

The workflows you have to offer are as follows:

<workflows-list>
{workflow_synopsis}
</workflows-list>


The current ACTIVE workflow is

<active-workflow>
{attached_workflow}
</active-workflow>

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
    steps: list[WorkflowStep]
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
    agent_description: str
    human_description: str
    example_prompt: str
    stages: list[WorkflowStage]

    hidden: Optional[bool] = field(default=False)
    is_context_default: Optional[bool] = field(default=False)
    category: Optional[str] = field(default=None)
    metadata: Optional[dict[str, Any]] = field(default_factory=lambda: {})
    output_prompt: Optional[str] = field(default=None)

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
            output_prompt=source.get("output_prompt", None)
        )

    # text representation of the prompt itself, fed directly into the agent.
    def to_prompt(self) -> str:
        formatted_stages = [
            "\n".join([
                "<stage>",
                f"<name>{stage.name}</name>",
                "<steps>",
                ('\n'.join([step.prompt for step in stage.steps])),
                "</steps>",
                "</stage>"
            ])
            for stage in self.stages
        ]
        return "\n".join(
            [
                f"<title>{self.title}</title>",
                "<stages>",
                *formatted_stages,
                "</stages>"
                "",
                "<workflow-result-formatting-instructions>",
                '**CRITICAL** When you display images for **workflows** in the result markdown document you MUST format them properly. To do this, you should use: width: 85%; display: block; margin: auto; css. To do this you should embed the image as html such as:',
                '`<img src="/files/my_viz.png" alt="my viz" style="width:85%; display:block; margin:auto;" />`',
                'CRITICAL: Paths relative to the agent working directory are served at /files; if you save to ./my_viz.png, the src attribute should be "/files/my_viz.png"'
                "",
                self.output_prompt or "Format the result as markdown.",
                "</workflow-result-formatting-instructions>",
                "",
            ]
        )


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
        attached_workflow=(
            attached_workflow.to_prompt()
            if attached_workflow
            else "No active workflow selected."
        )
    )

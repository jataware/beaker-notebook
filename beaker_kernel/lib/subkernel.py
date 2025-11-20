import abc
import asyncio
import json
from typing import Any, Callable, TYPE_CHECKING, ClassVar
import hashlib
import shutil
from tempfile import mkdtemp
import os
import os.path
import requests

from archytas.tool_utils import AgentRef, tool, LoopControllerRef, ReactContextRef

from .autodiscovery import autodiscover
from .utils import env_enabled, action, ExecutionTask, slugify
from .jupyter_kernel_proxy import ProxyKernelClient
from .config import config
from .context import BeakerContext, WorkflowStageProgress
from .code_analysis.analysis_types import AnalysisCodeCells

if TYPE_CHECKING:
    from langchain_core.messages import ToolMessage, AIMessage, BaseMessage, ToolCall
    from archytas.models.base import BaseArchytasModel
    from archytas.agent import Agent
    from archytas.chat_history import ChatHistory
    try:
        from tree_sitter import Language as TreeSitterLanguage
    except ImportError:
        from typing import Any as TreeSitterLanguage

Checkpoint = dict[str, str]


class JsonStateEncoder(json.JSONEncoder):
    pass


import logging
logger = logging.getLogger(__name__)


async def run_code_summarizer(message: "ToolMessage", chat_history: "ChatHistory", agent: "Agent", model: "BaseArchytasModel"):
    from langchain_core.messages import AIMessage
    size_threshold = 800
    excision_text_template = "...skipping {} characters..."
    split_percentage = 0.7
    text = message.text
    message_len = len(text)
    calling_record, tool_call = chat_history.get_tool_caller(message.tool_call_id)
    calling_message: AIMessage = calling_record.message
    code = tool_call.get("args", {}).get("code", "")
    code_len = len(code)

    if message_len > size_threshold:
        message_excision_label_len = len(excision_text_template) - 2 + len(str(message_len - size_threshold))
        message_excision_text = excision_text_template.format(message_len - size_threshold + message_excision_label_len)
        message_excision_start = int(size_threshold * split_percentage)
        message_excision_end = message_len - (size_threshold - message_excision_start - len(message_excision_text))

        message.additional_kwargs["orig_content"] = message.content
        message.content = "".join([
            text[:message_excision_start],
            message_excision_text,
            text[message_excision_end:],
        ])
    if code_len > size_threshold:
        code_excision_label_len = len(excision_text_template) - 2 + len(str(code_len - size_threshold))
        code_excision_text = excision_text_template.format(code_len - size_threshold + code_excision_label_len)
        code_excision_start = int(size_threshold * split_percentage)
        code_excision_end = code_len - (size_threshold - code_excision_start - len(code_excision_text))

        message.additional_kwargs["orig_code"] = code
        shortened_code = "".join([
            code[:code_excision_start],
            code_excision_text,
            code[code_excision_end:],
        ])

        tool_call["args"]["code"] = shortened_code

        if isinstance(calling_message.content, list):
            for content in calling_message.content:
                if (
                    isinstance(content, dict)
                    and content.get("type", None) == "tool_use"
                    and content.get("id", None) == message.tool_call_id
                ):
                    code_input = content.get("input", None)
                    if isinstance(code_input, dict) and "code" in code_input:
                        content["input"]["code"] = shortened_code
    message.artifact["summarized"] = True

@tool()
async def attach_workflow(workflow_title: str, agent: AgentRef):
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

@tool()
async def update_workflow_stage(stage_name: str, state: str, results: str, agent: AgentRef):
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

@tool()
async def update_workflow_output(results: str, agent: AgentRef):
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

@tool(autosummarize=True, summarizer=run_code_summarizer)
async def run_code(code: str, agent: AgentRef, loop: LoopControllerRef, react_context: ReactContextRef) -> str:
    """
    Executes code in the user's notebook on behalf of the user, but collects the outputs of the run for use by the Agent
    in the ReAct loop, if needed.

    The code runs in a new codecell and the user can watch the execution and will see all of the normal output in the
    Jupyter interface.

    This tool can be used to probe the user's environment or collect information to answer questions, or can be used to
    run code completely on behalf of the user. If a user asks the agent to do something that reasonably should be done
    via code, you should probably default to using this tool.

    This tool can be run more than once in a react loop. All actions and variables created in earlier uses of the tool
    in a particular loop should be assumed to exist for future uses of the tool in the same loop.

    Args:
        code (str): Code to run directly in Jupyter. This should be a string exactly as it would appear in a notebook
                    codecell. No extra escaping of newlines or similar characters is required.
    Returns:
        str: A summary of the run, along with the collected stdout, stderr, returned result, display_data items, and any
             errors that may have occurred.
    """
    def format_execution_context(context) -> str:
        """
        Formats the execution context into a format that is easy for the agent to parse and understand.
        """
        stdout_list = context.get("stdout_list")
        stderr_list = context.get("stderr_list")
        display_data_list = context.get("display_data_list")
        error = context.get("error")
        return_value = context.get("return")

        output = [
             """Execution report:""",
            f"""Execution id: {context['id']}""",
            f"""Successful?: {context['done'] and not context['error']}""",
            f"""Code executed:
```
{context['command']}
```\n""",
        ]

        if error:
            output.extend([
                 "The following error was thrown when executing the code",
                 "  Error:",
                f"    {error['ename']} {error['evalue']}",
                 "  TraceBack:",
                 "\n".join(error['traceback']),
                 "",
            ])


        if stdout_list:
            output.extend([
                "The execution produced the following stdout output:",
                "\n".join(["```", *stdout_list, "```\n"]),
            ])
        if stderr_list:
            output.extend([
                "The execution produced the following stderr output:",
                "\n".join(["```", *stderr_list, "```\n"]),
            ])
        if display_data_list:
            output.append(
                "The execution produced the following `display_data` objects to display in the notebook:",
            )
            for idx, display_data in enumerate(display_data_list):
                output.append(
                    f"display_data item {idx}:"
                )
                for mimetype, value in display_data.items():
                    if len(value) > 800:
                        value = f"{value[:400]} ... truncated ... {value[-400:]}"
                    output.append(
                        f"{mimetype}:"
                    )
                    output.append(
                        f"```\n{value}\n```\n"
                    )
        if return_value:
            output.append(
                "The execution returned the following:",
            )
            if isinstance(return_value, str):
                output.extend([
                    '```', return_value, '```\n'
                ])
        output.append("Execution Report Complete")
        return "\n".join(output)

    # TODO: In future, this may become a parameter and we allow the agent to decide if code should be automatically run
    # or just be added.
    autoexecute = True
    message = react_context.get("message", None)
    identities = getattr(message, 'identities', [])

    try:
        execution_task: ExecutionTask
        if isinstance(agent.context.subkernel, CheckpointableBeakerSubkernel) and is_checkpointing_enabled():
            checkpoint_index, execution_task = await agent.context.subkernel.checkpoint_and_execute(
                code, not autoexecute, parent_header=message.header, identities=identities
            )
        else:
            execution_task = agent.context.execute(
                code, store_history=True, surpress_messages=(not autoexecute), parent_header=message.header, identities=identities
            )
            checkpoint_index = None
        execute_request_msg = {
            name: getattr(execution_task.execute_request_msg, name)
            for name in execution_task.execute_request_msg.json_field_names
        }
        payload = {
            "action": "code_cell",
            "language": agent.context.subkernel.SLUG,
            "code": code.strip(),
            "autoexecute": autoexecute,
            "execute_request_msg": execute_request_msg,
        }
        if checkpoint_index is not None:
            payload["checkpoint_index"] = checkpoint_index
        agent.context.send_response(
            "iopub",
            "add_child_codecell",
            payload,
            parent_header=message.header,
            parent_identities=getattr(message, "identities", None),
        )

        execution_context = await execution_task

        try:
            preview_payload = await agent.context.preview()
            agent.context.send_response(
                "iopub",
                "preview",
                preview_payload,
                parent_header=message.header,
            )
        except Exception as e:
            logger.error(f"Successfully ran code, but failed to fetch preview: {e}")

        try:
            kernel_state_payload = await agent.context.kernel_state()
            agent.context.send_response(
                "iopub",
                "kernel_state_info",
                kernel_state_payload,
                parent_header=message.header,
            )
        except Exception as e:
            logger.error(f"Successfully ran code, but failed to fetch kernel state: {e}")

    except asyncio.CancelledError as err:
        logger.error("Code execution was interrupted by the user.")
        raise
    except Exception as err:
        logger.error(err, exc_info=err)
        raise

    return format_execution_context(execution_context)

class BeakerSubkernel(abc.ABC):
    DISPLAY_NAME: str
    SLUG: str
    KERNEL_NAME: str
    JUPYTER_LANGUAGE: str

    WEIGHT: int = 50  # Used for auto-sorting in drop-downs, etc. Lower weights are listed earlier.

    TOOLS: list[tuple[Callable, Callable]]  = [
        (run_code, lambda: True),
        # disabled in context.py if no workflows on context.
        # if the lambda below contains self -- self.context.workflows won't be
        # populated at the check time in tools(self)... so checking in context makes more sense.
        (attach_workflow, lambda: True),
        (update_workflow_stage, lambda: True),
        (update_workflow_output, lambda: True)
    ]

    FETCH_STATE_CODE: str = ""

    tasks: ClassVar[set[asyncio.Task]] = set()

    @classmethod
    @abc.abstractmethod
    def parse_subkernel_return(cls, execution_result) -> Any:
        ...

    @property
    def tools(self):
        return [tool for tool, condition in self.TOOLS if condition()]

    def __init__(self, jupyter_id: str, subkernel_configuration: dict, context: BeakerContext):
        self.kernel_id = jupyter_id
        self.connected_kernel = ProxyKernelClient(subkernel_configuration, session_id=context.beaker_kernel.session_id)
        self.context = context


    def get_treesitter_language(self) -> "TreeSitterLanguage":
        raise NotImplementedError()

    async def lint_code(self, cells: AnalysisCodeCells):
        pass

    async def shutdown(self, kernel_id) -> bool:
        try:
            logger.info(f"Shutting down connected subkernel {kernel_id}")
            res = requests.delete(
                f"{self.context.beaker_kernel.jupyter_server}/api/kernels/{kernel_id}",
                headers={"Authorization": f"token {config.jupyter_token}"},
            )
            if res.status_code == 204:
                return True
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as err:
            return False

    def cleanup(self):
        def finish_cleanup(task: asyncio.Task):
            success = task.result()
            if success:
                self.kernel_id = None
            self.tasks.discard(task)

        if self.kernel_id is not None:
            task = asyncio.create_task(self.shutdown(self.kernel_id))
            self.tasks.add(task)
            task.add_done_callback(finish_cleanup)

    def format_kernel_state(self, state: dict) -> dict:
        return state

# Provided for backwards compatibility
BaseSubkernel = BeakerSubkernel


def is_checkpointing_enabled():
    return getattr(config, "enable_checkpoints", True)


class CheckpointableBeakerSubkernel(BeakerSubkernel):
    SERIALIZATION_EXTENSION: str = "storage"

    def __init__(self, jupyter_id: str, subkernel_configuration: dict, context):
        super().__init__(jupyter_id, subkernel_configuration, context)
        self.checkpoints_enabled = is_checkpointing_enabled()
        self.storage_prefix = os.path.join(config.checkpoint_storage_path, self.kernel_id)
        self.checkpoints : list[Checkpoint] = []
        if self.checkpoints_enabled:
            os.makedirs(self.storage_prefix, exist_ok=True, mode=0o777)
            os.chmod(self.storage_prefix, 0o777)

    def store_serialization(self, filename: str) -> str:
        with open(filename, "rb") as file:
            chunksize = 4 * 1024 * 1024
            hash = hashlib.new("sha256")
            while chunk := file.read(chunksize):
                hash.update(chunk)
            identifier = hash.hexdigest()
            new_filename = f"{self.storage_prefix}/{identifier}.{self.SERIALIZATION_EXTENSION}"

        shutil.move(filename, new_filename)
        return new_filename

    @abc.abstractmethod
    async def generate_checkpoint_from_state(self) -> Checkpoint:
        ...

    @abc.abstractmethod
    async def load_checkpoint(self, checkpoint: Checkpoint):
        ...

    async def add_checkpoint(self) :
        if not self.checkpoints_enabled:
            raise RuntimeError("Checkpoints are not enabled")
        fetched_checkpoint = await self.generate_checkpoint_from_state()
        checkpoint = {
            varname: self.store_serialization(filename) for
            varname, filename in fetched_checkpoint.items()
        }
        self.checkpoints.append(checkpoint)
        return len(self.checkpoints) - 1


    async def rollback(self, checkpoint_index: int):
        if not self.checkpoints_enabled:
            raise RuntimeError("Checkpoints are not enabled")
        if checkpoint_index >= len(self.checkpoints):
            raise IndexError(f"Checkpoint at index {checkpoint_index} does not exist")
        checkpoint = self.checkpoints[checkpoint_index]
        await self.load_checkpoint(checkpoint)
        self.checkpoints = self.checkpoints[:checkpoint_index + 1]

    @action(action_name="rollback", enabled=is_checkpointing_enabled)
    async def rollback_action(self, message):
        checkpoint_index = message.content.get("checkpoint_index", None)
        await self.rollback(checkpoint_index)
    rollback_action._default_payload = "{\n\t\"checkpoint_index\": 0\n}"

    @action(action_name="add_checkpoint", enabled=is_checkpointing_enabled)
    async def add_checkpoint_action(self, message):
        return await self.add_checkpoint()
    add_checkpoint_action._default_payload = "{}"


    def cleanup(self):
        super().cleanup()
        if self.checkpoints_enabled:
            shutil.rmtree(self.storage_prefix, ignore_errors=True)
            self.checkpoints = []

    async def checkpoint_and_execute(self, code: str, surpress_messages: bool = False, parent_header = None, identities = None) -> tuple[int, ExecutionTask]:
        checkpoint_index = await self.add_checkpoint()
        task = self.context.execute(code, store_history=True, surpress_messages=surpress_messages, parent_header=parent_header, identities=identities)
        return checkpoint_index, task

    async def execute_and_rollback(self, code: str, surpress_messages: bool = False, parent_header = None, identities=None):
        checkpoint_index = await self.add_checkpoint()
        result = await self.context.execute(code, surpress_messages=surpress_messages, parent_header=parent_header, identities=identities)
        await self.rollback(checkpoint_index)
        return str(result["return"])

# Provided for backwards compatibility
BaseCheckpointableSubkernel = CheckpointableBeakerSubkernel


def autodiscover_subkernels():
    return autodiscover("subkernels")

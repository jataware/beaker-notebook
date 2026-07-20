import abc
import asyncio
import hashlib
import inspect
import json
import os
import os.path
import shutil
import requests
import yaml
from tempfile import mkdtemp
from typing import Any, Callable, Optional, TYPE_CHECKING, ClassVar

from archytas.tool_utils import AgentRef, tool, statetool, LoopControllerRef, ReactContextRef

from .autodiscovery import autodiscover
from .utils import env_enabled, action, ExecutionTask, slugify, url_path_join
from .jupyter_kernel_proxy import ProxyKernelClient
from .config import config
from .context import BeakerContext, WorkflowStageProgress
from .code_analysis.analysis_types import AnalysisCodeCells
from .reflector import ReflectorRegistry

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


class BeakerSubkernel(abc.ABC):
    DISPLAY_NAME: str
    SLUG: str
    KERNEL_NAME: str | None = None  # Optional hint; if set and available, preferred when resolving kernel specs
    JUPYTER_LANGUAGE: str

    WEIGHT: int = 50  # Used for auto-sorting in drop-downs, etc. Lower weights are listed earlier.

    procedure_location: ClassVar[Optional[os.PathLike | str]] = None
    """
    Override to point at a non-default procedures directory. By default,
    procedures are expected at ``<dir of subkernel module>/procedures/``.
    """

    KERNEL_STATE_SAMPLE_BUDGET: ClassVar[int] = 300
    """
    Per-call sample-byte budget applied to ``kernel_state`` payloads. Subkernels
    may override per-language; ``config.kernel_state_sample_budget`` overrides
    further at the deployment level if set.
    """

    DESCRIBE_VARIABLES_SAMPLE_BUDGET: ClassVar[int] = 1500
    """
    Per-call sample-byte budget applied to ``describe_variables`` payloads.
    Subkernels may override per-language; ``config.describe_variables_sample_budget``
    overrides at the deployment level if set.
    """

    EXCLUDED_LOCAL_NAMES: ClassVar[frozenset[str]] = frozenset()
    """
    Names that should not appear in the ``local_names`` payload. Per-language
    subkernels extend this with their own framework-noise sets (e.g. Python
    adds ``In``, ``Out``, ``get_ipython``, etc.). Underscore-prefixed names are
    filtered separately by the fetch_state template convention.
    """

    reflectors: ReflectorRegistry
    """
    Registry of reflectors discovered for this subkernel. Populated during
    context setup once the merged Jinja environment is built; before that it
    is an empty registry.
    """

    @classmethod
    def resolve_kernelspec(cls, kernelspecs: dict[str, dict]) -> str | None:
        """Given the kernelspecs dict from the KSM API, return the spec name to use.

        Prefers KERNEL_NAME if set and available, otherwise picks any spec
        matching JUPYTER_LANGUAGE. Subclasses can override for custom logic.

        Args:
            kernelspecs: The "kernelspecs" dict from the /api/kernelspecs response,
                         mapping spec name -> {"name": ..., "spec": {"language": ..., ...}, ...}
        """
        if cls.KERNEL_NAME and cls.KERNEL_NAME in kernelspecs:
            return cls.KERNEL_NAME

        matches = [
            name for name, info in kernelspecs.items()
            if info.get("spec", {}).get("language") == cls.JUPYTER_LANGUAGE
        ]
        if matches:
            return matches[0]
        return None

    FETCH_STATE_CODE: str = ""

    tasks: ClassVar[set[asyncio.Task]] = set()

    async def system_preamble(self) -> str | None:
        """Contribution to the cacheable system_preamble layer.

        Default produces a short block describing the runtime. Subclasses may
        override to provide richer descriptions.
        """
        doc = (self.__class__.__doc__ or "").strip()
        parts = [
            f"Subkernel: {self.DISPLAY_NAME} (language: {self.JUPYTER_LANGUAGE})"
        ]
        if doc:
            parts.append(doc)
        data = {
            "usage": [
                "This is information regarding the Jupyter kernel environment that your notebook, ",
                "and the code you write, are running in."
            ],
            "subkernel": {
                "name": self.DISPLAY_NAME,
                "language": self.JUPYTER_LANGUAGE,
                "docstring": doc or None,
            },
        }
        yaml_text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False).rstrip("\n")
        return f"""
## Runtime environment

```yaml
{yaml_text}
```
        """.strip()

    @classmethod
    @abc.abstractmethod
    def parse_subkernel_return(cls, execution_result) -> Any:
        ...

    @property
    def tools(self):
        return [self]

    def __init__(self, jupyter_id: str, subkernel_configuration: dict, context: BeakerContext):
        self.kernel_id = jupyter_id
        self.connected_kernel = ProxyKernelClient(subkernel_configuration, session_id=context.beaker_kernel.session_id)
        self.context = context
        self.reflectors = ReflectorRegistry()

    @classmethod
    def _resolve_procedure_dirs(cls) -> list[str]:
        """Return the list of directories to discover procedures from for this
        subkernel, in resolution order.

        Today this is just one directory — either ``cls.procedure_location`` if
        explicitly set, or ``<dir of subkernel module>/procedures/`` derived
        from the class's source location. Returned as a list to leave room for
        future multi-dir resolution without changing the caller contract.

        Non-existent directories are filtered out so the caller can blindly
        feed the result into a ``FileSystemLoader``.
        """
        candidate: str
        if cls.procedure_location is not None:
            candidate = os.fspath(cls.procedure_location)
            if not os.path.isabs(candidate):
                module_file = inspect.getfile(cls)
                candidate = os.path.normpath(
                    os.path.join(os.path.dirname(module_file), candidate)
                )
        else:
            module_file = inspect.getfile(cls)
            candidate = os.path.join(os.path.dirname(module_file), "procedures")
        return [candidate] if os.path.isdir(candidate) else []

    def _is_kernelstate_enabled(self):
        return bool(config.send_kernel_state)

    def _has_kernelstate(self):
        """True when this subkernel has a fetch_state procedure registered, or
        a legacy FETCH_STATE_CODE class attribute (deprecated)."""
        if "fetch_state" in (self.context.templates or {}):
            return True
        return bool(self.FETCH_STATE_CODE)

    def _state_condition(self):
        return self._is_kernelstate_enabled() and self._has_kernelstate()

    def _render_fetch_state_code(self) -> str:
        """Render the fetch_state procedure for the current subkernel.

        Prefers the ``fetch_state`` Jinja procedure (procedure-backed path).
        Falls back to the legacy ``FETCH_STATE_CODE`` class attribute with a
        DeprecationWarning if no procedure is registered.
        """
        if "fetch_state" in (self.context.templates or {}):
            return self.context.get_code(
                "fetch_state",
                {
                    "reflectors": list(self.reflectors.values()),
                    "excluded_local_names": sorted(self.EXCLUDED_LOCAL_NAMES),
                },
            )
        legacy = self.FETCH_STATE_CODE
        if legacy:
            import warnings
            warnings.warn(
                f"{type(self).__name__} relies on the deprecated "
                f"FETCH_STATE_CODE class attribute. Migrate to a "
                f"procedure-backed fetch_state.<ext> template; see "
                f"beaker_kernel.lib.kernel_state for the canonical schema.",
                DeprecationWarning,
                stacklevel=2,
            )
            return legacy
        return ""

    async def _get_state(self):
        if not (self._is_kernelstate_enabled() or self._has_kernelstate()):
            return None
        fetch_state_code = self._render_fetch_state_code()
        if not fetch_state_code:
            return None
        result = await self.context.evaluate(fetch_state_code)
        state = result.get("return", {})
        return state

    def _kernel_state_budget(self) -> int:
        cfg_budget = getattr(config, "kernel_state_sample_budget", 0) or 0
        if cfg_budget > 0:
            return cfg_budget
        return self.KERNEL_STATE_SAMPLE_BUDGET

    def _describe_variables_budget(self) -> int:
        cfg_budget = getattr(config, "describe_variables_sample_budget", 0) or 0
        if cfg_budget > 0:
            return cfg_budget
        return self.DESCRIBE_VARIABLES_SAMPLE_BUDGET

    @statetool(condition=_state_condition)
    async def kernel_state(self):
        """
        Returns the state of the running kernel.

        Produces a canonical KernelStatePayload (local_names + variables),
        applies the configured sample-byte budget, and renders the agent-
        facing markdown block.
        """
        from beaker_notebook.lib.kernel_state import (
            apply_sample_budget,
            render_agent_payload,
        )
        state = await self._get_state()
        if not state:
            return ""
        if not isinstance(state, dict):
            # Legacy fetch returned something other than a dict; surface raw.
            return f"## Kernel state\n```application/json\n{json.dumps(state, cls=JsonStateEncoder, indent=2)}\n```\n"
        state.setdefault("local_names", {})
        state.setdefault("variables", {})
        apply_sample_budget(state, self._kernel_state_budget())
        return render_agent_payload(state)

    @tool(internal=True)
    async def describe_variables(self, names: list[str], agent: AgentRef) -> str:
        """
        Return a richer description of one or more variables in the running kernel.

        Use this when the inline kernel_state summary is too thin (e.g., you need
        a sample of a DataFrame's contents, the dtype of an array, or the keys
        of a dict). Pass the names you want as a list; missing names are
        reported back so you can adjust.

        Args:
            names (list[str]): Names of the variables in the running kernel to
                               describe. Pass one or more names per call.

        Returns:
            str: A markdown block containing the structured descriptions and a
                 list of any names that weren't found in the kernel.
        """
        from beaker_notebook.lib.kernel_state import apply_sample_budget
        if not names:
            return "describe_variables called with no names; pass at least one."
        if "describe_variables" not in (self.context.templates or {}):
            return (
                "This subkernel does not provide a describe_variables procedure. "
                "Use run_code to inspect variables directly."
            )
        code = self.context.get_code(
            "describe_variables",
            {
                "reflectors": list(self.reflectors.values()),
                "target_names": list(names),
            },
        )
        result = await self.context.evaluate(code)
        payload = result.get("return") or {}
        variables = payload.get("variables") or {}
        missing = payload.get("missing") or []

        # Apply describe-level budget (different ceiling than kernel_state).
        apply_sample_budget(
            {"variables": variables},
            self._describe_variables_budget(),
        )

        sections = ["## Variable descriptions"]
        if variables:
            sections.append(
                "```application/json\n"
                + json.dumps(variables, indent=2, default=str)
                + "\n```"
            )
        if missing:
            sections.append(
                "Names not found in the kernel: "
                + ", ".join(f"`{n}`" for n in missing)
            )
        return "\n\n".join(sections)

    @tool(autosummarize=True, summarizer=run_code_summarizer, internal=True)
    async def run_code(self, code: str, agent: AgentRef, loop: LoopControllerRef, react_context: ReactContextRef) -> str:
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
        However, calls of this tool must always be made serially, with no more than one call per ReAct loop iteration.
        All code executes in a shared, stateful kernel — variables and side effects from one call persist into the next,
        so execution order matters.

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
                        value = str(value)
                        if len(value) > 200:
                            value = f"{value[:100]} ... truncated ... {value[-100:]}"
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
            # Checkpointing is temporarily disabled: serializing kernel state can take several minutes in
            # some cases, which makes the per-execution checkpoint unworkable. We plan to revisit this in
            # a future update. Until then, code is executed directly without a surrounding checkpoint.
            # if isinstance(agent.context.subkernel, CheckpointableBeakerSubkernel) and is_checkpointing_enabled():
            #     checkpoint_index, execution_task = await agent.context.subkernel.checkpoint_and_execute(
            #         code, not autoexecute, parent_header=message.header, identities=identities
            #     )
            # else:
            execution_task = agent.context.execute(
                code, store_history=True, surpress_messages=(not autoexecute), parent_header=message.header, identities=identities
            )
            # checkpoint_index = None
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
            # if checkpoint_index is not None:
            #     payload["checkpoint_index"] = checkpoint_index
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

    def get_treesitter_language(self) -> "TreeSitterLanguage":
        raise NotImplementedError()

    async def lint_code(self, cells: AnalysisCodeCells):
        pass

    async def shutdown(self, kernel_id) -> bool:
        try:
            logger.info(f"Shutting down connected subkernel {kernel_id}")
            res = requests.delete(
                url_path_join(self.context.beaker_kernel.jupyter_server, "/api/kernels/", str(kernel_id)),
                headers={
                    "X-AUTH-BEAKER": self.context.beaker_kernel.api_auth()
                },
            )
            if res.status_code == 204:
                return True
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as err:
            return False

    async def cleanup(self):
        if self.kernel_id is not None:
            success = await self.shutdown(self.kernel_id)
            if success:
                self.kernel_id = None

    def format_kernel_state(self, state: dict) -> dict:
        return state

# Provided for backwards compatibility
BaseSubkernel = BeakerSubkernel


def is_checkpointing_enabled():
    # Checkpointing is temporarily disabled regardless of the `enable_checkpoints` config flag.
    # Serializing kernel state can take several minutes in some cases, which makes the
    # checkpoint-per-execution model unusable in practice. The implementation is preserved below
    # and we plan to revisit it in a future update once state serialization can be made fast and
    # bounded. To re-enable, restore the commented-out body in place of the unconditional False.
    return False
    # return getattr(config, "enable_checkpoints", True)


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


    async def cleanup(self):
        await super().cleanup()
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

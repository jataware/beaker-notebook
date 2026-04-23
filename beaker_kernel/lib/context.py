import asyncio
import base64
import dataclasses
import inspect
import itertools
import json
import logging
import os
import os.path
import re
import requests
import urllib.parse
from dataclasses import asdict
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple, ClassVar, Awaitable, TypedDict, Literal, TypeAlias, Collection
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, Template, select_autoescape
import yaml

from beaker_kernel.lib.autodiscovery import autodiscover
from beaker_kernel.lib.utils import action, get_socket, ExecutionTask, get_execution_context, get_parent_message, ExecutionError, ensure_async
from beaker_kernel.lib.config import config as beaker_config
from beaker_kernel.lib.integrations.base import BaseIntegrationProvider
from beaker_kernel.lib.integrations.registry import IntegrationProviderRegistry
from beaker_kernel.lib.integrations.types import Integration
from beaker_kernel.lib.workflow import Workflow, WorkflowState, WorkflowStageProgress, create_available_workflows_prompt


from .jupyter_kernel_proxy import InterceptionFilter, JupyterMessage

if TYPE_CHECKING:
    from archytas.react import ReActAgent

    from beaker_kernel.kernel import BeakerKernel

    from .agent import BeakerAgent
    from .subkernel import BeakerSubkernel

logger = logging.getLogger(__name__)

TOOL_TOGGLE_PREFIX = "TOOL_ENABLED_"


class LinterCodeCellPayload(TypedDict):
    cell_id: str
    content: str


class LinterCodeCellsPayload(TypedDict):
    notebook_id: str
    cells: list[LinterCodeCellPayload]


class BeakerContext:
    SLUG: ClassVar[str]
    SHORT_NAME: ClassVar[str]
    FULL_NAME: ClassVar[str]
    WEIGHT: ClassVar[int] = 50  # Used for auto-sorting in drop-downs, etc. Lower weights are listed earlier.
    AGENT_CLS: "ClassVar[type[BeakerAgent]]"
    ASSET_DIR: ClassVar[Optional[os.PathLike|str]] = None
    RENDERERS: ClassVar[Optional[Dict[str, Dict[str, str]]]] = None
    INTEGRATION_PROVIDERS: ClassVar[list[tuple[type[BaseIntegrationProvider], tuple, dict[str, Any]]]] = []

    beaker_kernel: "BeakerKernel"
    subkernel: "BeakerSubkernel"
    config: Dict[str, Any]
    agent: "BeakerAgent"
    current_llm_query: str | None
    compatible_subkernels: ClassVar[list[str] | None] = None

    intercepts: List[Tuple[str, Callable, str]]
    jinja_env: Optional[Environment]
    templates: Dict[str, Template]

    workflows: Dict[str, Workflow]
    current_workflow_state: Optional[WorkflowState]

    preview_function_name: str = "generate_preview"
    kernel_state_function_name: str = "send_kernel_state"

    notebook_state: Optional[dict]
    integrations: IntegrationProviderRegistry

    procedure_location: ClassVar[Optional[os.PathLike|str]]

    def __init__(
        self,
        beaker_kernel: "BeakerKernel",
        agent_cls: "Optional[type[BeakerAgent]]" = None,
        config: Optional[Dict[str, Any]] = None,
        integrations: Optional[list[BaseIntegrationProvider]] = None
    ):
        if integrations is None:
            integrations = []
        if agent_cls is None:
            agent_cls = self.AGENT_CLS
        integrations.extend((*self.default_integration_providers, *self.extra_integration_providers()))

        self.intercepts = []
        self.integrations = IntegrationProviderRegistry(integrations)
        self.jinja_env = None
        self.templates = {}
        self.workflows = self.discover_workflows()
        self.current_workflow_state = None
        self.beaker_kernel = beaker_kernel
        self.config = config or {}
        self.subkernel = self.get_subkernel()

        self.agent = agent_cls(
            context=self,
            tools=self.subkernel.tools,
        )

        self.current_llm_query = None
        self.notebook_state = None

        self.disable_tools()

        # Add intercepts, by inspecting the instance and extracting matching methods
        self._collect_and_register_intercepts(self)
        self._collect_and_register_intercepts(self.subkernel)

        # Set auto-context from agent
        if getattr(self, "auto_context", None) is not None:
            self.agent.set_auto_context("Default context", self.auto_context)

        class_dir = inspect.getfile(self.__class__)
        code_dir = os.path.join(os.path.dirname(class_dir), "procedures", self.subkernel.SLUG)
        if os.path.exists(code_dir):
            self.jinja_env = Environment(
                loader=FileSystemLoader(code_dir),
                autoescape=select_autoescape()
            )

            for template_file in self.jinja_env.list_templates():
                if template_file.startswith('__'):
                    continue
                try:
                    template_name, _ = os.path.splitext(template_file)
                    template = self.jinja_env.get_template(template_file)
                    self.templates[template_name] = template
                except UnicodeDecodeError:
                    # For templates, this indicates a binary file which can't be a template, so throw a warning and skip.
                    logger.warning(f"File '{template_name}' in context '{self.__class__.__name__}' is not a valid template file as it cannot be decoded to a unicode string.")

        for workflow_id, workflow in self.workflows.items():
            if workflow.is_context_default:
                self.attach_workflow(workflow_id)
        if not self.workflows:
            logger.warning("Context has no workflows: disabling tools.")
            workflow_tools = [
                "attach_workflow",
                "update_workflow_stage",
                "update_workflow_output"
            ]
            for workflow_tool in workflow_tools:
                self.agent.disable(workflow_tool)

    def __init_subclass__(cls):
        mod = inspect.getmodule(cls)
        # Initialize default values for class variables if not already set
        if not hasattr(cls, "AGENT_CLS") and hasattr(cls, "agent_cls"):
            cls.AGENT_CLS = cls.agent_cls
        if not hasattr(cls, "SLUG"):
            package_str = mod.__package__
            if package_str:
                cls.SLUG = package_str.split(".")[-1]
            else:
                cls.SLUG = cls.__name__.upper()
        if not hasattr(cls, "SHORT_NAME"):
            cls.SHORT_NAME = cls.SLUG.title()
        full_name = getattr(cls, "FULL_NAME", None)
        if full_name is not None:
            # Check if full name is inherited from parent. If so, it should be recreated based on this class.
            parents = cls.mro()
            if full_name == getattr(parents[0], "FULL_NAME", None) == getattr(parents[1], "FULL_NAME", None):
                full_name = None
        if full_name is None:
            full_name = cls.__name__
            full_name = re.sub(r'Context$', '', full_name)
            full_name = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', full_name)
            cls.FULL_NAME = full_name

        if (asset_dir := getattr(cls, "ASSET_DIR", None)):
            # If the path is absolute, assume that it is still relative to the directory which contains the context file.
            # e.g. if it's set to "/static" assume it should be "/path/to/package/my_context/static"
            if os.path.isabs(asset_dir):
                asset_dir = f".{asset_dir}"
            mod_path = Path(inspect.getabsfile(cls)).parent
            asset_path = mod_path / asset_dir
            if asset_path.exists() and asset_path.is_dir():
                setattr(cls, "ASSET_DIR", str(asset_path))

            renderers = getattr(cls, "RENDERERS", None)
            if renderers and asset_path.is_dir():
                for mimetype, config in renderers.items():
                    renderer_file = config.get("file", "renderers.js")
                    renderer_path = asset_path / renderer_file
                    if not (renderer_path.exists() and renderer_path.is_file()):
                        logger.warning(
                            f"Renderer file '{renderer_file}' for mime type '{mimetype}' "
                            f"not found in asset dir for context '{cls.__name__}'."
                        )

        # If a subclass has an auto_context, it should be used instead of the parent's.
        subclass_autocontext = getattr(cls, "auto_context", None)
        if not (subclass_autocontext is None or subclass_autocontext is BeakerContext.auto_context):
            cls._auto_context = subclass_autocontext
            cls.auto_context = BeakerContext.auto_context

    @property
    def preview(self) -> Callable[[], Awaitable[Any]] | None:
        preview_func = getattr(self, self.preview_function_name, None)
        if callable(preview_func) and not inspect.iscoroutinefunction(preview_func):
            raise ValueError(f"Preview function '{self.preview_function_name}' must be a coroutine (awaitable) if defined.")
        if preview_func and inspect.iscoroutinefunction(preview_func):
            return preview_func

    @property
    def kernel_state(self) -> Callable[[], Awaitable[Any]] | None:
        state_func = getattr(self, self.kernel_state_function_name, None)
        if callable(state_func) and not inspect.iscoroutinefunction(state_func):
            raise ValueError(f"Kernel state fetching function '{self.kernel_state_function_name}' must be a coroutine (awaitable) if defined.")
        if state_func and inspect.iscoroutinefunction(state_func):
            return state_func

    @property
    def default_integration_providers(self) -> set[BaseIntegrationProvider]:
        from beaker_kernel.lib.integrations.skill import SkillIntegrationProvider
        return { SkillIntegrationProvider("Default Skills"), }

    @classmethod
    def extra_integration_providers(cls) -> set[BaseIntegrationProvider]:
        integrations = set()
        for integration_cls, args, kwargs in cls.INTEGRATION_PROVIDERS:
            integrations.add(integration_cls(*args, **kwargs))
        return integrations

    def disable_tools(self):
        # TODO: Identical toolnames don't work
        toggles = beaker_config.tools_enabled
        toggles.update({
            attr.removeprefix(TOOL_TOGGLE_PREFIX).lower(): value == "true"
            for attr, value in os.environ.items() if attr.startswith(TOOL_TOGGLE_PREFIX)
        })
        toggles.update({
            attr.removeprefix(TOOL_TOGGLE_PREFIX).lower(): getattr(self, attr)
            for attr in dir(self) if attr.startswith(TOOL_TOGGLE_PREFIX)
        })
        disabled_tools = [
            tool
            for tool, enabled in toggles.items() if not enabled
        ]
        self.agent.disable(*disabled_tools)

    async def setup(self, context_info=None, parent_header=None):
        if context_info:
            self.config["context_info"] = context_info

        if callable(getattr(self.agent, 'setup', None)):
            await self.agent.setup(self.config["context_info"], parent_header=parent_header)

        preamble = await self.default_preamble()
        if preamble:
            self.agent.chat_history.set_user_preamble_text(preamble)

    def cleanup(self):
        self.subkernel.cleanup()
        for msg_type, intercept_func, stream in self.intercepts:
            self.beaker_kernel.remove_intercept(msg_type=msg_type, func=intercept_func, stream=stream)
        del self.agent

    def _collect_and_register_intercepts(self, target):
        for _, method in inspect.getmembers(target, lambda member: inspect.ismethod(member) and hasattr(member, "_intercept")):
            msg_type, stream = getattr(method, "_intercept")
            self.intercepts.append((msg_type, method, stream))
            self.beaker_kernel.add_intercept(msg_type=msg_type, func=method, stream=stream)

    async def default_preamble(self) -> Optional[str]:
        return None

    async def auto_context(self):
        parts = []
        if hasattr(self, "_auto_context"):
            result = await ensure_async(self._auto_context())
            parts.append(
                result
            )
        if beaker_config.send_kernel_state:
            kernel_state = await self.get_subkernel_state()
            if kernel_state:
                parts.append(f"""\
## Kernel state
```application/json
{json.dumps(kernel_state)}
```\
""")
        if beaker_config.send_notebook_state:
            if self.notebook_state:
                parts.append(f"""\
## Current notebook
```application/x-ipynb+json
{json.dumps(self.notebook_state)}
```
Note: In the notebook representation above, communication with the agent is encoded as Markdown cells with metadata
field "beaker_cell_type" = "query". If a cell has metadata field "parent_cell", then the agent generated this cell as
part of the ReAct loop associated with that query. As such, cells that follow a query may have occured while the ReAact
loop was running and chronologically fit "inside" the query cell, as opposed to having been run afterwards.\
""")

        if self.workflows:
            parts.append(
                create_available_workflows_prompt(
                    list(self.workflows.values()),
                    self.attached_workflow
                )
            )

        if self.integrations:
            parts.append("Here are integrations that you have access to:")
            integration_prompts = [
                integration.prompt for integration in self.integrations
            ]
            parts.append("---".join(integration_prompts))
        content = "\n\n".join(parts)
        return content

    def get_subkernel(self):
        subkernel_slug = self.config.get("subkernel", None)
        language = self.config.get("language", None)

        # Step 1: Discover available BeakerSubkernel classes
        subkernels = autodiscover("subkernels")  # slug -> class

        # Step 2: Resolve which BeakerSubkernel class to use
        subkernel_cls: type[BeakerSubkernel] | None = None
        if subkernel_slug and subkernel_slug in subkernels:
            subkernel_cls = subkernels[subkernel_slug]
        elif language:
            by_lang = {s.JUPYTER_LANGUAGE: s for s in subkernels.values()}
            subkernel_cls = by_lang.get(language)
        if subkernel_cls is None:
            raise ValueError(
                f"No subkernel found for subkernel={subkernel_slug!r}, language={language!r}. "
                f"Available subkernels: {list(subkernels.keys())}"
            )

        # Step 3: Fetch kernel specs from the (potentially remote) KSM
        urlbase = self.beaker_kernel.jupyter_server
        kernelspecs_res = requests.get(
            urllib.parse.urljoin(urlbase, "/api/kernelspecs"),
            headers={"X-AUTH-BEAKER": self.beaker_kernel.api_auth()},
        )
        if kernelspecs_res.status_code >= 400:
            raise RuntimeError(
                f"Error fetching kernel specs (status {kernelspecs_res.status_code}): "
                f"{kernelspecs_res.text}"
            )
        kernelspecs = kernelspecs_res.json().get("kernelspecs", {})

        # Step 4: Resolve which kernel spec name to use for kernel creation
        kernel_spec_name = subkernel_cls.resolve_kernelspec(kernelspecs)
        if not kernel_spec_name:
            available_languages = {
                info.get("spec", {}).get("language") for info in kernelspecs.values()
            }
            raise ValueError(
                f"No installed kernel spec matches subkernel '{subkernel_cls.SLUG}' "
                f"(language='{subkernel_cls.JUPYTER_LANGUAGE}'). "
                f"Available kernel spec languages: {available_languages}"
            )

        # Step 5: Create the kernel via the Jupyter API
        path = self.beaker_kernel.session_config.get("beaker_session", None)
        if path is None:
            path = self.beaker_kernel.session_config.get("jupyter_session", "")

        kernel_creation_res = requests.post(
            url=urllib.parse.urljoin(urlbase, "/api/kernels"),
            json={"name": kernel_spec_name, "path": path},
            headers={"X-AUTH-BEAKER": self.beaker_kernel.api_auth()},
        )
        kernel_info = kernel_creation_res.json()

        try:
            subkernel_id: str = kernel_info["id"]
        except Exception as err:
            logger.error(json.dumps(kernel_info), exc_info=err)
            raise

        connection_info_res = requests.get(
            url=urllib.parse.urljoin(urlbase, f"/beaker/subkernels/{subkernel_id}"),
            headers={"X-AUTH-BEAKER": self.beaker_kernel.api_auth()},
        )
        connection_info = connection_info_res.json()
        connection_info["key"] = base64.b64decode(connection_info.get("key", b""))

        # Step 6: Instantiate the BeakerSubkernel
        subkernel: BeakerSubkernel = subkernel_cls(subkernel_id, connection_info, self)
        self.beaker_kernel.server.set_proxy_target(subkernel.connected_kernel)
        return subkernel

    @classmethod
    def available_subkernels(cls) -> dict["str", "BeakerSubkernel"]:
        subkernels: Dict[str, BeakerSubkernel] = autodiscover("subkernels")

        if cls.compatible_subkernels:
            return {slug: subkernels[slug] for slug in cls.compatible_subkernels if slug in subkernels}

        class_dir = inspect.getfile(cls)
        proc_dir = os.path.join(os.path.dirname(class_dir), "procedures")
        if os.path.exists(proc_dir):
            proc_slugs = list(os.listdir(proc_dir))
        else:
            proc_slugs = None
        subkernel_list = sorted(subkernels.values(), key=lambda subkernel: (subkernel.WEIGHT, subkernel.SLUG))

        if proc_slugs and subkernel_list:
            result = {subkernel.SLUG: subkernel for subkernel in subkernel_list if subkernel.SLUG in proc_slugs}
            return result
        else:
            return {}

    @classmethod
    def default_payload(cls) -> str:
        class_dir = inspect.getfile(cls)
        payload_file_path = os.path.join(os.path.dirname(class_dir), "default_payload.json")
        if os.path.exists(payload_file_path):
            with open(payload_file_path) as payload_file:
                return payload_file.read().strip()
        else:
            return "{}"

    async def get_info(self) -> dict:
        """

        """
        custom_messages = {
            message_type: {
                "func": f"{intercept_func.__module__}.{intercept_func.__class__.__name__}.{intercept_func.__name__}",
                "docs": getattr(intercept_func, "_docs", None),
                "default_payload": getattr(intercept_func, "_default_payload", None),
            }
            for message_type, intercept_func, _ in self.intercepts
            if getattr(intercept_func, "_action", None) is None
        }
        action_details = {
            intercept_func._action: {
                "intercept": message_type,
                "func": f"{intercept_func.__module__}.{intercept_func.__class__.__name__}.{intercept_func.__name__}",
                "docs": getattr(intercept_func, "_docs", None),
                "default_payload": getattr(intercept_func, "_default_payload", None),
            }
            for message_type, intercept_func, _ in self.intercepts
            if getattr(intercept_func, "_action", None) is not None
            and getattr(intercept_func, "_scope", None) in ["external", "global"]
        }
        if self.agent:
            agent_details = self.agent.get_info()
        else:
            agent_details = None

        workflow_info = {
            "state": self.current_workflow_state,
            "workflows": {
                uuid: asdict(workflow)
                for uuid, workflow in self.workflows.items()
            }
        }
        custom_renderers = {}
        if self.RENDERERS:
            for mimetype, config in self.RENDERERS.items():
                renderer_file = config.get("file", "renderers.js")
                export_name = config.get("export", "default")
                custom_renderers[mimetype] = {
                    "url": f"/assets/context/{self.SLUG}/{renderer_file}",
                    "name": export_name,
                }

        payload = {
            "language": self.subkernel.JUPYTER_LANGUAGE,
            "subkernel": self.subkernel.SLUG,
            "config": self.config,
            "actions": action_details,
            "custom_messages": custom_messages,
            "procedures": list(self.templates.keys()),
            "workflow_info": workflow_info,
            "agent": agent_details,
            "debug": self.beaker_kernel.debug_enabled,
            "verbose": self.beaker_kernel.verbose,
            "custom_renderers": custom_renderers,
        }

        return payload

    async def list_providers(self):
        if not self.integrations:
            return {}
        return {
            provider.slug: {
                "display_name": provider.display_name,
                "mutable": provider.mutable,
            }
            for provider in self.integrations
        }

    async def list_integrations(self):
        if not self.integrations:
            return {}
        # return as uuid->integration mapping for faster search/lookup on receiver
        return {
            integration.uuid: asdict(integration)
            for integration in itertools.chain(
                *[provider.list_integrations() or [] for provider in self.integrations]
            )
        }

    def _call_message_result_wrapper_inner(self, object):
        return asdict(object) if dataclasses.is_dataclass(object) else str(object) # type: ignore

    def _call_message_result_wrapper(self, object):
        return json.loads(json.dumps(object, default=self._call_message_result_wrapper_inner))

    @action(scope="internal")
    async def call_in_context(self, message):
        content = message.content
        args = content.get("args", [])
        kwargs = content.get("kwargs", {})
        target_text = content.get("target", "")
        target_type, target_id = target_text.split(":", maxsplit=1) if ":" in target_text else (target_text, None)

        match target_type:
            # context methods
            case "context":
                function = getattr(self, content.get("function"))
                result = await ensure_async(function(*args, **kwargs))
                result = self._call_message_result_wrapper(result)
            # calling directly on a provider itself -- `provider:adhoc:my_adhoc_provider`
            case "provider":
                if target_id is None:
                    msg = "Provider targets must specify desired provider: e.g. `provider:my_provider`"
                    raise ValueError(msg)
                _provider_type, provider_id = target_id.split(":", maxsplit=1)
                try:
                    provider = next(
                        provider for provider in self.integrations
                        if provider.id == provider_id
                    )
                    function = getattr(provider, content.get("function"))
                    result = await ensure_async(function(*args, **kwargs))
                    result = self._call_message_result_wrapper(result)
                except StopIteration as e:
                    msg = f"Provider not found in integrations. `{provider_id}` not in {[p.slug for p in self.integrations]}"
                    raise KeyError(msg) from e
            # mapping from an integration uuid to its parent provider, to call a method on that parent
            case "integration":
                all_integrations = list(itertools.chain(
                    *[provider.list_integrations() or [] for provider in self.integrations]
                ))
                try:
                    integration = next(
                        integration for integration in all_integrations
                        if integration.uuid == target_id
                    )
                except StopIteration as e:
                    msg = f"Integration `{target_id}` not found in {[i.slug for i in all_integrations]}"
                    raise KeyError(msg) from e
                _provider_type, provider_id = integration.provider.split(":", maxsplit=1)
                try:
                    provider = next(
                        provider for provider in self.integrations
                        if provider.slug == provider_id
                    )
                except StopIteration as e:
                    msg = f"Provider not found: `{provider_id}` in {[provider.slug for provider in self.integrations]}"
                    raise KeyError(msg) from e
                function = getattr(provider, content.get("function"))
                result = await ensure_async(function(*args, **kwargs))
                result = self._call_message_result_wrapper(result)
            case _:
                raise NotImplementedError
        return result

    async def get_subkernel_state(self):
        fetch_state_code = self.subkernel.FETCH_STATE_CODE
        state = await self.evaluate(fetch_state_code)
        for warning in state["stderr_list"]:
            logger.warning(warning)
        return state["return"]

    async def send_kernel_state(self):
        """
        Gets the subkernel state and also applies subkernel formatting as to
        prepare it for display.
        """
        state = await self.get_subkernel_state()
        return {
            "x-application/beaker-subkernel-state": {
                "application/json": self.subkernel.format_kernel_state(state or {})
            },
        }

    @action(action_name="get_subkernel_state")
    async def get_subkernel_state_action(self, message):
        """
        Fetches the state of the subkernel, including all defined variables, imports, and functions.
        """
        state = await self.get_subkernel_state()
        self.send_response(
            stream="iopub",
            msg_or_type="get_subkernel_state_response",
            content=state,
            parent_header=message.header,
        )
        return state
    get_subkernel_state_action._default_payload = "{}"

    @action()
    async def get_agent_history(self, message):
        """
        Returns all of the history for the LLM agent.
        """
        ## Handling de/serialization of langchain messages should live in Archytas instead.
        from langchain_core.load import dumps

        # kernel_state_future = self.get_subkernel_state()
        # notebook_state_future = self.beaker_kernel.request_notebook_state(parent_message=message)
        # kernel_state, notebook_state = await asyncio.gather(kernel_state_future, notebook_state_future)
        # with self.prepare_state(kernel_state, notebook_state):

        # auto_context will be set by the agent - only rehydrate system + user/AI messages
        # otherwise `await self.agent.all_messages()` would be easy here
        messages = []
        if self.agent.chat_history.system_message:
            messages.append(dumps(self.agent.chat_history.system_message.message))

        for record in self.agent.chat_history.raw_records:
            history_message = record.message
            messages.append(dumps(history_message))

        return messages
    get_agent_history._default_payload = '{}'

    @action()
    async def set_agent_history(self, message):
        """
        Sets the message history of the agent to the contents of the message,
        updating chat history as well.
        """
        from langchain_core.load import loads
        from archytas.chat_history import ChatHistory

        system = message.content.pop(0)
        history_messages = [loads(history_message)
                            for history_message in message.content]
        self.agent.chat_history = ChatHistory(history_messages)
        self.agent.chat_history.set_system_message(loads(system))

        if getattr(self, "auto_context", None) is not None:
            self.agent.set_auto_context("Default context", self.auto_context)
            self.agent.chat_history.auto_context_message._model = self.agent.model
            # ensure hashes don't align and content updates
            self.agent.chat_history.auto_context_message.content = ""
            await self.agent.chat_history.auto_context_message.update_content()
        await self.agent.chat_history.token_estimate(model=self.agent.model)
        await self.beaker_kernel.send_chat_history(parent_header=message.header)

    get_agent_history._default_payload = '{}'

    @action()
    async def set_user_preamble(self, message):
        content = message.content
        new_message_text: str = content.get("message_text", "")

        if not self.agent or not self.agent.chat_history:
            self.send_response(
                stream="iopub",
                msg_or_type="stream",
                content={
                    "name": "stderr",
                    "text": "Error: No active context or chat history available"
                },
                parent_header=message.header,
            )
            return {"success": False, "error": "No active context"}

        # Create a HumanMessage and add it to chat history
        preamble_text = new_message_text.strip()
        self.agent.chat_history.set_user_preamble_text(preamble_text)

        # Send success response
        self.send_response(
            stream="iopub",
            msg_or_type="stream",
            content={
                "name": "stdout",
                "text": f"Message added to chat history: {new_message_text.strip()}"
            },
            parent_header=message.header,
        )

        # Send updated chat history
        await self.beaker_kernel.send_chat_history(message.header)

        return {"success": True, "message": "Message added to chat history"}

    set_user_preamble._default_payload = """\
{
    "message_text": ""
}
"""

    @action(default_payload='{}')
    async def get_preview(self, message):
        """
        Returns the current preview payload if enabled, otherwise None.
        """
        return await self.preview()

    @property
    def attached_workflow(self) -> Workflow | None:
        return self.workflows.get(self.current_workflow_state["workflow_id"], None) if self.current_workflow_state else None

    def attach_workflow(self, workflow_id: str | None):
        if workflow_id is None:
            self.current_workflow_state = None
        else:
            self.current_workflow_state = WorkflowState.from_workflow(
                workflow_id=workflow_id,
                workflow=self.workflows[workflow_id]
            )
        self.send_response("iopub", "update_workflow_state", self.current_workflow_state)

    @action()
    async def set_workflow(self, message):
        self.attach_workflow(message.content["workflow"])

    @action(default_payload=LinterCodeCellsPayload(notebook_id='nb1', cells=[LinterCodeCellPayload(cell_id='cell1', content='import os\nos.exit(0)')]))
    async def lint_code(self, message):
        """
        """
        from .code_analysis.analyzer import AnalysisEngine
        from .code_analysis.analysis_types import AnalysisCodeCell, AnalysisCodeCells, AnalysisAnnotations
        from .code_analysis.rules.trust.rules import all_rules, ast_rules, llm_rules

        Mode: TypeAlias = Literal["fast", "thorough"]

        message_content: LinterCodeCellsPayload = message.content
        notebook_id = message_content.get("notebook_id", "foo")
        mode: Mode = message_content.get("mode", "thorough")
        cells = AnalysisCodeCells([
            AnalysisCodeCell(notebook_id=notebook_id, **cell) for cell in message_content["cells"]
        ])

        language = self.subkernel.get_treesitter_language()
        if mode == "fast":
            rules = ast_rules
        elif mode == "thorough":
            rules = all_rules
        analyzer = AnalysisEngine(rules=rules, language=language, context=self)
        result_set: AnalysisAnnotations
        async for result_set in analyzer.analyze_iter(cells):
            content = [result.model_dump() for result in result_set]
            self.send_response("iopub", "lint_code_result", content=content)


    def send_response(self, stream, msg_or_type, content=None, channel=None, parent_header={}, parent_identities=None):
        return self.beaker_kernel.send_response(stream, msg_or_type, content, channel, parent_header, parent_identities)

    @classmethod
    def discover_procedures(cls) -> dict:
        proc_dir = getattr(cls, "procedure_location", None)
        result = {}
        if proc_dir is None:
            class_dir = os.path.dirname(inspect.getfile(cls))
            proc_dir = os.path.join(class_dir, "procedures")
        if not proc_dir or not os.path.isdir(proc_dir):
            return {}

        langdirs = os.listdir(proc_dir)
        for lang in langdirs:
            proc_lang_dir = os.path.join(proc_dir, lang)
            if os.path.exists(proc_lang_dir):
                for proc_file in os.listdir(proc_lang_dir):
                    proc_name, _ = os.path.splitext(proc_file)
                    if proc_name.startswith('.'):
                        continue
                    file_path = os.path.join(lang, proc_file)
                    if proc_name not in result:
                        result[proc_name] = {
                            "name": proc_name,
                            "languages": {lang: file_path}
                        }
                    else:
                        result[proc_name]["languages"][lang] = file_path
        return result

    @classmethod
    def discover_workflows(cls) -> dict:
        workflow_dir = getattr(cls, "workflow_location", None)
        result = {}

        if workflow_dir is None:
            class_dir = os.path.dirname(inspect.getfile(cls))
            workflow_dir = os.path.join(class_dir, "workflows")
        if workflow_dir and not os.path.isabs(workflow_dir):
            class_dir = os.path.dirname(inspect.getfile(cls))
            workflow_dir = os.path.normpath(os.path.join(class_dir, workflow_dir))
        if os.path.isdir(workflow_dir):
            for workflow_yaml in Path(workflow_dir).glob("*.yaml"):
                workflow = Workflow.from_yaml(yaml.safe_load(workflow_yaml.read_text()))
                # lives as long as the session does
                workflow_id = str(uuid4())
                result[workflow_id] = workflow
        return result

    @property
    def slug(self) -> Optional[str]:
        """
        A short, white-space-free label used to identify the context programatically.
        """
        return self.SLUG

    @property
    def lang(self):
        return self.subkernel.KERNEL_NAME

    @property
    def metadata(self):
        try:
            return json.loads(self.get_code('metadata'))
        except ValueError:
            return {}

    def get_code(self, name, render_dict: Dict[str, Any]=None) -> str:
        if render_dict is None:
            render_dict = {}
        template = self.templates.get(name, None)
        if template is None:
            raise ValueError(
                f"'{name}' is not a defined procedure for context '{self.__class__.__name__}' and "
                f"subkernel '{self.subkernel.DISPLAY_NAME} ({self.subkernel.KERNEL_NAME})'"
            )
        return template.render(**render_dict)

    def execute(self,
        command,
        response_handler=None,
        parent_header={},
        store_history=False,
        surpress_messages=True,
        identities=None,
        cc_messages=True,
        raise_on_error=True,
    ) -> ExecutionTask:

        self.beaker_kernel.debug("execution_start", {"command": command}, parent_header=parent_header)
        stream = self.subkernel.connected_kernel.streams.shell

        execution_context = get_execution_context() or {}
        outer_parent_context = get_parent_message() or {}

        if identities is None:
            identities = []

        execute_request_multipart = self.subkernel.connected_kernel.make_multipart_message(
            msg_type="execute_request",
            content={
                "silent": False,
                "store_history": store_history,
                "user_expressions": {},
                "allow_stdin": True,
                "stop_on_error": False,
                "code": command,
            },
            parent_header=parent_header,
            metadata={
                "trusted": True,
            },
            identities=identities,
        )
        execute_request_msg = JupyterMessage.parse(execute_request_multipart)
        async def execution_coro():
            stream.send_multipart(execute_request_multipart)
            message_id = execute_request_msg.header.get("msg_id")
            self.beaker_kernel.internal_executions.add(message_id)

            message_context = {
                "id": message_id,
                "command": command,
                "stdout_list": [],
                "stderr_list": [],
                "display_data_list": [],
                "return": None,
                "error": None,
                "done": False,
                "result": None,
                "parent": execute_request_msg,
            }
            message_metadata = {}

            filter_list = self.beaker_kernel.server.filters

            shell_socket = get_socket("shell")
            iopub_socket = get_socket("iopub")

            # Internal decorator to send relabeled copies of certain messages to the front-end
            def carbon_copy(fn):
                @wraps(fn)
                def inner_relabel(server, target_stream, data):
                    if cc_messages:
                        message = JupyterMessage.parse(data)
                        msg_type = message.header.get('msg_type')

                        destination_server = server.manager.server
                        destination_stream = destination_server.streams.iopub

                        relabeled_message = JupyterMessage(*message)
                        context_type = execution_context.get("type", "unknown")
                        context_name = execution_context.get("name", None)

                        original_parent_message: JupyterMessage = outer_parent_context.get("parent_message")
                        if original_parent_message:
                            # As this is a tuple, we can't update the reference pointed to by
                            # `relabled_message.parent_header` but we can  change the values of the referenced dict
                            parent_header: dict = relabeled_message.parent_header
                            parent_header.clear()
                            parent_header.update(original_parent_message.header)

                        relabeled_message.header["msg_type"] = f"beaker__{msg_type}"
                        relabeled_message.content["execution_type"] = context_type
                        if context_name:
                            relabeled_message.content["execution_item_name"] = context_name
                        relabeled_data = relabeled_message.sign_using(destination_server.config.get("key")).parts
                        destination_stream.send_multipart(relabeled_data)
                        destination_stream.flush()

                    return fn(server, target_stream, data)
                return inner_relabel


            # Generate a handler to catch and silence the output
            @carbon_copy
            async def silence_message(server, target_stream, data):
                message = JupyterMessage.parse(data)

                if not surpress_messages or message.parent_header.get("msg_id", None) != message_id:
                    return data
                return None

            async def collect_result(server, target_stream, data):
                message = JupyterMessage.parse(data)
                # Ensure we are only working on handlers for this message response
                if message.parent_header.get("msg_id", None) != message_id:
                    return data

                content_data = message.content["data"].get("text/plain", None)
                message_context["return"] = content_data
                if not surpress_messages:
                    return data

            async def collect_display_data(server, target_stream, data):
                message = JupyterMessage.parse(data)
                # Ensure we are only working on handlers for this message response
                if message.parent_header.get("msg_id", None) != message_id:
                    return data
                display_data = message.content["data"]
                message_context["display_data_list"].append(display_data)
                if not surpress_messages:
                    return data

            async def collect_stream(server, target_stream, data):
                message = JupyterMessage.parse(data)
                # Ensure we are only working on handlers for this message response
                if message.parent_header.get("msg_id", None) != message_id:
                    return data
                stream = message.content["name"]
                message_context[f"{stream}_list"].append(message.content["text"])
                if not surpress_messages:
                    return data

            @carbon_copy
            async def handle_error(server, target_stream, data):
                message = JupyterMessage.parse(data)
                content = message.content
                message_context["error"] = content
                logger.error(
                    "Error: %s %s\nTraceback:\n%s",
                    content["ename"],
                    content["evalue"],
                    "\n".join(content["traceback"]),
                )
                if raise_on_error:
                    raise ExecutionError(content["ename"], content["evalue"], content["traceback"])
                if not surpress_messages:
                    return data

            @carbon_copy
            async def cleanup(server, target_stream, data):
                message = JupyterMessage.parse(data)
                # Ensure we are only working on handlers for this message response
                if message.parent_header.get("msg_id", None) != message_id:
                    return data
                if response_handler:
                    filter_list.remove(
                        InterceptionFilter(iopub_socket, "stream", response_handler)
                    )
                filter_list.remove(
                    InterceptionFilter(iopub_socket, "stream", collect_stream)
                )
                filter_list.remove(
                    InterceptionFilter(iopub_socket, "display_data", collect_display_data)
                )
                filter_list.remove(
                    InterceptionFilter(iopub_socket, "execute_input", silence_message)
                )
                filter_list.remove(
                    InterceptionFilter(iopub_socket, "execute_request", silence_message)
                )
                filter_list.remove(
                    InterceptionFilter(iopub_socket, "execute_result", collect_result)
                )
                filter_list.remove(InterceptionFilter(iopub_socket, "error", handle_error))
                filter_list.remove(
                    InterceptionFilter(shell_socket, "execute_reply", cleanup)
                )
                message_context["result"] = message.content
                message_context["done"] = True
                if not surpress_messages:
                    return data

            filter_list.append(
                InterceptionFilter(iopub_socket, "execute_input", silence_message)
            )
            filter_list.append(
                InterceptionFilter(iopub_socket, "execute_request", silence_message)
            )
            filter_list.append(
                InterceptionFilter(iopub_socket, "execute_result", collect_result)
            )
            filter_list.append(InterceptionFilter(shell_socket, "execute_reply", cleanup))
            filter_list.append(InterceptionFilter(iopub_socket, "stream", collect_stream))
            filter_list.append(InterceptionFilter(iopub_socket, "display_data", collect_display_data))
            filter_list.append(InterceptionFilter(iopub_socket, "error", handle_error))

            if response_handler:
                filter_list.append(
                    InterceptionFilter(iopub_socket, "stream", response_handler)
                )

            await asyncio.sleep(0.1)
            while not message_context["done"]:
                await asyncio.sleep(0.2)
            # Wait for any straggling messages
            await asyncio.sleep(0.2)
            self.beaker_kernel.internal_executions.remove(message_id)
            self.beaker_kernel.debug("execution_end", message_context, parent_header=parent_header)
            return message_context
        task = ExecutionTask(coro=execution_coro(), execute_request_msg=execute_request_msg)
        return task

    async def evaluate(self, expression, parent_header={}):
        result = await self.execute(expression, parent_header=parent_header)
        try:
            parsed_result = self.subkernel.parse_subkernel_return(result)
            result["return"] = parsed_result
        except Exception:
            logger.error("Unable to parse result.")
            logger.debug("Subkernel: %s\nResult:\n%s", self.subkernel.connected_kernel, result)
        return result

# Provided for backwards compatibility
BaseContext = BeakerContext

def autodiscover_contexts():
    return autodiscover("contexts")

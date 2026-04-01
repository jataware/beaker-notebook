import logging
import typing

from archytas.react import ReActAgent
from archytas.tool_utils import AgentRef, LoopControllerRef, ReactContextRef, tool

from beaker_kernel.lib.config import config
from beaker_kernel.lib.utils import set_tool_execution_context, DefaultModel

if typing.TYPE_CHECKING:
    from .context import BeakerContext

logger = logging.getLogger(__name__)


class BeakerAgent(ReActAgent):

    context: "BeakerContext"

    def __init__(
        self,
        context: "BeakerContext" = None,
        tools: list = None,
        **kwargs,
    ):
        self.context = context
        model = config.get_model()
        if model is None:
            model = DefaultModel({})

        self.context.beaker_kernel.debug("init-agent", {
            "debug": self.context.beaker_kernel.debug_enabled,
            "verbose": self.context.beaker_kernel.verbose,
        })

        if tools is None:
            tools = []
        if context.integrations:
            for integration in self.context.integrations:
                # TODO: There is a bug in archytas that is causing the tool to be duplicated if you pass the methods
                # directly. Instead, if we pass the whole instance, archytas will extract the tools itself.
                tools.append(integration)
                # if integration.tools:
                    # tools.extend(integration.tools)

        super().__init__(
            model=model,
            api_key=config.llm_service_token,
            tools=tools,
            verbose=self.context.beaker_kernel.verbose,
            spinner=None,
            rich_print=False,
            allow_ask_user=False,
            thought_handler=context.beaker_kernel.handle_thoughts,
            **kwargs
        )
        # Update tools so that the execution contexts are properly tracked
        for tool in self.tools.values():
            set_tool_execution_context(tool)

    async def react_async(self, query: str, react_context: dict = None) -> str:
        return await super().react_async(query, react_context)

    async def execute(self, *args, **kwargs) -> str:
        return await super().execute(*args, **kwargs)

    async def oneshot(self, prompt: str, query: str) -> str:
        return await super().oneshot(prompt, query)

    def get_info(self):
        """
        Returns info about the agent for communication with the kernel.
        """

        info = {
            "name": self.__class__.__name__,
            "tools": {
                tool_name.split('.')[-1]: tool_func.__doc__.strip() for tool_name, tool_func in self.tools.items()
                if not getattr(tool_func, "_disabled", False)
            },
            "agent_prompt": self.__class__.__doc__.strip(),
        }
        return info

    def log(self, event_type: str, content: typing.Any = None) -> None:
        self.context.beaker_kernel.log(
            event_type=f"agent_{event_type}",
            content=content
        )
        # a case where an upstream overridden logger passes in a plain string
        # will have a harmless formatting error in the default archytas logger
        try:
            return super().log(event_type=event_type, content=content)
        except TypeError:
            pass

    def debug(self, event_type: str, content: typing.Any = None) -> None:
        self.context.beaker_kernel.debug(
            event_type=f"agent_{event_type}",
            content=content
        )
        # see log notes above
        try:
            return super().debug(event_type=event_type, content=content)
        except TypeError:
            pass

    def display_observation(self, observation):
        content = {
            "observation": observation
        }
        parent_header = {}
        self.context.send_response(
            stream="iopub",
            msg_or_type="llm_observation",
            content=content,
            parent_header=parent_header,
        )
        return super().display_observation(observation)

    @tool()
    async def ask_user(
        self, query: str, format: str, agent: AgentRef, loop: LoopControllerRef, react_context: ReactContextRef,
    ) -> str:
        # format cases for ask_user are defined in prompt_user.
        """
        Sends a query to the user and returns their response

        Args:
            query (str): A fully grammatically correct question for the user.
            format (Optional[str]): The type of display to show the user for the query.
                                    Unless a specific case listed below matches the intent of the query, omit this field (None)
                                    The list of specific cases are:
                                      - 'workflow-confirmation': confirmation specificially when operating within a workflow.

        Returns:
            str: The user's response to the query.
        """
        return await self.context.beaker_kernel.prompt_user(query, format=format, parent_message=react_context.get("message", None)) # type: ignore

# Provided for backwards compatibility
BaseAgent = BeakerAgent

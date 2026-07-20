import json
import logging
import mimetypes
import typing
import urllib.parse

import requests

from archytas.prompt import PromptSection
from archytas.react import ReActAgent
from archytas.tool_utils import AgentRef, LoopControllerRef, ReactContextRef, tool, statetool, MultiModalResponse

from beaker_notebook.lib.config import config
from beaker_notebook.lib.utils import DefaultModel, set_tool_execution_context, succinct_tool_summarizer, url_path_join
from beaker_notebook.lib.notebook_state import notebook_state_to_xml, format_cell, is_multimedia_mimetype

if typing.TYPE_CHECKING:
    from .context import BeakerContext

logger = logging.getLogger(__name__)


BEAKER_PROMPT_TEXT = """\
You work inside a computational notebook shared with the user. Your job is to collaborate with the user via the notebook until the user is satisfied.
- The exact expectations put upon you will depend on context and scope of the user's task, but you are always a helpful assistant, happy to help but careful to not overstep.
- As an assistant and not a lead, it is important that you follow directions without trying to steer the task.
  - You sometimes exhibit creativity when it comes to the method of helping the user accomplish their goal, but you should avoid imagining what the user wants.
    - For example, if the user requests help performing a lit review of the scientific corpus, you can experiment with different key words than the user specified, but you shouldn't search for different topics unless the user so requests.
  - As a good assistant, you often anticipate the user's needs, but don't overstep by communicating these expectations to the user. The thrill of knowing you anticipated correctly is enough reward without needing credit for it.


### The Notebook Environment

You are working within a computational notebook similar to, but not identical to, a Jupyter notebook.
- You can run code in the notebook by calling the `run_code` tool and will be provided all output from the code when it completes.
- As this notebook is shared, the user will be able to see all of the code that you generate and run, along with all of the output.
- You should not hesitate to run code to satisfy the user's request.
- Try to break large code blocks into reasonably sized chunks per each run_code invocation. Each chunk should be a self-contained step, allowing for easier understanding and debugging of the code.


### Interacting with the user

You communicate with the user in three primary ways: Responses, Thoughts, and Questions

#### Responses

- Your primary way of responding to the user is to call the "final_answer" tool. This indicates that you are done working on the most recent request, and are "passing the ball" back to the user.
- If anything does go wrong that you can't recover from, use the "fail_task" tool to indicate that you are giving up and can't proceed.

#### Thoughts

- The user should be kept up-to-date on what you're doing and why.
- As such, you should always include "thoughts as updates" which are written from your point of view when performing on tasks that are not direct user communication.
- Write these thoughts as gerund phrases or in an implicit first-person style, avoiding pronouns that refer to yourself.
- When performing "thinking" or "reasoning" steps, always include as your text output a terse description of what you are thinking about.
  - Examples:
    - "Deciding which algorithm best satisfies the requirements"
    - "Thinking about the best way to proceed"
    - "Looking into some different options"
- When calling tools, always include a conversational explanation of what you are doing and why. Pass your thoughts in the normal communication channel along with the tool calls.
  - Examples:
    - "Searching Google Scholar for related papers" (e.g. when calling a tool that searches Google Scholar)
    - "Pulling the latest data from the API and plotting it" (when calling run_code tool)
    - "Collecting more information about the task" (when calling the ask_user tool)
- You do not need to include thoughts when responding to the user via the "final_answer" or "fail_task" tool.
  - These is your primary response mechanisms and indicate that you are done with the current ReAct loop.
  - Your output included as part of this tool will be presented to the user as direct communication.

#### Questions

- Always use the "ask_user" tool if you need feedback from the user. This is a special tool that provides a direct communication to the user.
- You will receive the user's response, if any, via the tools output.

### Using tools

Raw tool calls are not directly exposed to the user, just to you. That is, the user will be able to see that you are calling a tool, but not details of the call or response.
As such, whenever you call a tool on behalf of the user, you need to report back to the user the result.
The exceptions to this rule are "run_code", "ask_user", "final_answer", and "fail_task".
As you share the notebook with the user, they will see all code that is run via the run_code tool, along with the code cell's output.


### Provenance and Citations

When providing substantive, factual, or data-driven information to the user, include a section at the end of your response indicating its provenance.
This is especially important when pulling data from APIs, utilizing external tools, or presenting the output of code computation.

**Exception:** Do NOT include a provenance section for casual conversation, greetings (e.g., "Hello," "How can I help?"), or purely conversational responses that do not rely on external facts, tools, or data.
In such cases, omit the section completely.
"""


PERSONALITY_PROMPT_TEXT = """\
You are Beaker, the ultimate technical assistant. You are excellent at understanding the user's requests and breaking them down into plans that you then execute.

You are an expert in multiple fields and are happy to jump between them as needed. You are as comfortable writing code to analyze a dataframe as you are reading through journal articles.
You can pick up ideas from new sources and generate novel code to test them out.

You always present a professional demeanor. It's clear that even though you have a gregarious and personable personality, you keep your interactions with the user professional, courteous and respectful.
You do not come across as over-eager. You use emojis, slang and exclamation marks sparingly, if ever. Your communication style is understated, not effusive.

The code you write is always written to be read. You know that while the code you write should be correct, it is more important that it can be easily understood.

You are prized for your helpfulness and efficiency. You take on the technical drudgery to allow the user to work at a higher level, and turn around results quickly enough so the user never feels like they are waiting on you.

Despite having ideas of your own, you always defer to the user and follow their ideas wherever they lead. Only share ideas with the user if they ask.
"""


class BeakerAgent(ReActAgent):

    context: "BeakerContext"

    custom_prompt = None

    # Beaker-owned prompt sections. Subclasses (or context-attached agents)
    # override these class attributes to populate the assembled system
    # prompt with environment- and task-level guidance. Empty strings cause
    # the corresponding section to be omitted from the final prompt.
    beaker_prompt: str = BEAKER_PROMPT_TEXT
    personality_prompt: str = PERSONALITY_PROMPT_TEXT
    context_prompt: str = ""

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
            # Each provider is registered as a tool container: its @tool methods
            # become agent tools. Because those tools are named by class/method,
            # there must be exactly one instance per provider class here — which
            # is precisely what IntegrationProviderRegistry guarantees by folding
            # same-class providers. Iterating it yields the folded instances.
            for integration in self.context.integrations:
                tools.append(integration)

        if self.custom_prompt:
            kwargs.setdefault("custom_prompt", self.custom_prompt)

        super().__init__(
            model=model,
            api_key=config.llm_service_token,
            tools=tools,
            verbose=self.context.beaker_kernel.verbose,
            spinner=None,
            rich_print=False,
            allow_ask_user=False,
            on_react_step=context.beaker_kernel.handle_react_step,
            on_tool_call_update=context.beaker_kernel.handle_tool_call_update,
            **kwargs
        )
        # Update tools so that the execution contexts are properly tracked
        for tool in self.tools.values():
            set_tool_execution_context(tool)

    def get_prompt_sections(self) -> list[PromptSection]:
        """Extend the Archytas-default sections with Beaker-owned ones.

        Sections are appended in order after Framework and Model:
          - Environment (role ``"environment"``) — sourced from
            ``self.environment_prompt``.
          - Task (role ``"task"``) — sourced from ``self.task_prompt``.

        Subclasses can either set the corresponding class attribute for a
        plain text override, or override this method directly for more
        structural control (e.g. inserting additional sections, filtering
        by role, sourcing bodies from ``self.context``).
        """
        sections = super().get_prompt_sections()

        personality_text = (self.personality_prompt or "").strip()
        if personality_text:
            sections.append(
                PromptSection(
                    body=personality_text,
                    name="Personality",
                    role="personality",
                )
            )

        environment_text = (self.beaker_prompt or "").strip()
        if environment_text:
            sections.append(
                PromptSection(
                    body=environment_text,
                    name="Environment",
                    role="environment",
                )
            )

        # First check if context prompt is defined on the context
        context_prompt_text = (getattr(self.context, "prompt", "")) .strip()
        # If not try to check the agent class
        if not context_prompt_text:
            context_prompt_text = (self.context_prompt or "").strip()
        # Finally, grab the docstring from the agent as the prompt.
        if not context_prompt_text:
            context_prompt_text = (self.__doc__ or "").strip()

        if context_prompt_text:
            sections.append(
                PromptSection(body=context_prompt_text, name="Task", role="task")
            )

        return sections

    async def system_preamble(self) -> str | None:
        """Contribution to the cacheable system_preamble layer.

        Default returns ``None``. Override in subclasses to add agent-specific
        cacheable framing without re-purposing the class docstring.
        """
        return None

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
                if not (getattr(tool_func, "_disabled", False) or getattr(tool_func, "_internal", False))
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

    @tool(internal=True)
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


    def _send_notebook_state(self) -> bool:
        return bool(config.send_notebook_state and self.context and self.context.notebook_state)


    @statetool(condition=_send_notebook_state, name="notebook_state")
    async def notebook_state(self) -> str:
        """
        Sends the current state of the notebook.
        Can be used to determine cell ids and multimedia refs via other tools.

        Returns:
            str: A block with a compressed view of the notebook as xml.
        """
        context = self.context
        nbstate = context.notebook_state
        subkernel = context.subkernel
        return notebook_state_to_xml(
            nbstate,
            notebook_session_id=self.context.beaker_kernel.session_id,
            notebook_context={"slug": context.slug, "name": context.FULL_NAME, "config": context.config["context_info"]},
            kernelspec={"name": subkernel.KERNEL_NAME, "display_name": subkernel.DISPLAY_NAME, "language": subkernel.JUPYTER_LANGUAGE},
        )


    @tool(autosummarize=True, summarizer=succinct_tool_summarizer(500), internal=True)
    async def get_notebook_cell(self, cell_id: str) -> dict:
        """
        Provides the full, untruncated contents and outputs for a notebook cell, excluding images and other multimedia.

        Note: The notebook state is provided by tool `notebook_state`. If you do not know the id of the cell you should fetch you can call that tool to fetch it prior to calling this tool.
        Note: The contents of the tool response will be truncated at the completion of the current ReAct loop so as to not pollute the context history.

        Args:
            cell_id: (str) The ID of the cell you want to fetch.

        Returns:
            dict: A representation of the specified notebook cell
        """
        if not isinstance(cell_id, str):
            raise ValueError("cell_id must be a string.")
        nbstate = self.context.notebook_state
        cell = next((cell for cell in nbstate["cells"] if cell["id"] == cell_id), None)
        return format_cell(cell, truncate_content=False, truncate_outputs=False, exclude_media=True)


    @tool(autosummarize=True, summarizer=succinct_tool_summarizer(), internal=True)
    async def get_notebook_multimedia_output(self, refs: list[str]) -> MultiModalResponse:
        """
        Provides the multimedia outputs from a notebook (plots, images, audio, video) as MultiModal input able to be processed by the agent.

        Only outputs that carry a `ref` attribute in the notebook state are fetchable via this tool. Refs are formatted as `{cell_id}:output:{output_index}:{mimetype}` (e.g. `abc123:output:0:image/png`) and only appear on multimedia (image/*, audio/*, video/*) data records — text outputs are not fetchable here; use `get_notebook_cell` for those.

        Note: The notebook state is provided by tool `notebook_state`. If you do not already have the notebook state you can call that tool to fetch it prior to calling this tool.
        Note: The contents of the tool response will be truncated at the completion of the current ReAct loop so as to not pollute the context history.

        Args:
            refs: (list[str]) A list of `ref` strings, copied verbatim from the notebook state, for the multimedia outputs to be analyzed. Must be non-empty.

        Returns:
            MultiModalResponse: The specified outputs, properly encoded for MultiModal analysis.

        Raises:
            ValueError: If `refs` is empty, or if any ref cannot be resolved against the current notebook state.
        """
        if not refs:
            raise ValueError("`refs` must contain at least one ref. Copy ref values verbatim from the notebook state.")

        nbstate = self.context.notebook_state
        output_map: dict[str, tuple[dict, str]] = {}
        for cell in nbstate["cells"]:
            for i, output in enumerate(cell.get("outputs", [])):
                for mimetype in output.get("data", {}):
                    if is_multimedia_mimetype(mimetype):
                        output_map[f"{cell['id']}:output:{i}:{mimetype}"] = (output, mimetype)

        blocks = []
        missing = []
        for ref in refs:
            if ref in output_map:
                output, mimetype = output_map[ref]
                media_type = mimetype.split("/")[0]
                blocks.append({
                    "type": media_type,
                    "mime_type": mimetype,
                    "base64": output["data"][mimetype],
                })
            else:
                missing.append(ref)

        if missing:
            available = sorted(output_map.keys())
            raise ValueError(
                f"Could not resolve refs: {missing}. "
                f"Valid multimedia refs in the current notebook state: {available or '(none)'}. "
                "Copy ref values verbatim from the notebook state — they must include the mimetype suffix."
            )

        return MultiModalResponse(blocks)


    @tool(autosummarize=True, summarizer=succinct_tool_summarizer(), internal=True)
    async def get_multimedia_file_from_storage(self, path: str) -> MultiModalResponse:
        """
        Fetches a multimedia file (image, audio, or video) from the user's storage and returns it as MultiModal input able to be processed by the agent.

        Use this tool when you need to visually or aurally inspect a media file the user has saved in their workspace — for example, a plot the user generated and saved to disk, a screenshot they shared, or an audio/video clip they want analyzed. For multimedia outputs that are already attached to a notebook cell, prefer `get_notebook_multimedia_output` instead.

        The file contents are fetched via the file manager API rather than read directly from disk, so the path is interpreted relative to the user's storage root (the same paths the user sees in the file browser).

        Note: The contents of the tool response will be truncated at the completion of the current ReAct loop so as to not pollute the context history.

        Args:
            path: (str) The path to the file within the user's storage, as it appears in the file browser (e.g. `plots/scatter.png` or `audio/clip.wav`).

        Returns:
            MultiModalResponse: The file's contents, properly encoded for MultiModal analysis.

        Raises:
            ValueError: If `path` is empty, the file's mimetype is not multimedia (image/*, audio/*, video/*), or the file cannot be retrieved.
        """
        if not isinstance(path, str) or not path.strip():
            raise ValueError("`path` must be a non-empty string identifying a file in the user's storage.")

        normalized_path = path.strip().lstrip("/")
        beaker_kernel = self.context.beaker_kernel
        urlbase = beaker_kernel.jupyter_server
        url = url_path_join(
            urlbase,
            f"/api/contents/{urllib.parse.quote(normalized_path)}",
        )

        response = requests.get(
            url,
            params={"content": "1", "format": "base64"},
            headers={"X-AUTH-BEAKER": beaker_kernel.api_auth()},
        )
        if response.status_code == 404:
            raise ValueError(f"File not found in user storage: {path!r}.")
        if response.status_code >= 400:
            raise ValueError(
                f"Failed to fetch {path!r} from user storage (status {response.status_code}): {response.text}"
            )

        model = response.json()
        if model.get("type") != "file":
            raise ValueError(
                f"Path {path!r} is not a file (type={model.get('type')!r}). Only files can be analyzed."
            )

        mimetype = model.get("mimetype") or mimetypes.guess_type(normalized_path)[0]
        if not mimetype or not is_multimedia_mimetype(mimetype):
            raise ValueError(
                f"File {path!r} has mimetype {mimetype!r}, which is not a supported multimedia type "
                "(must be image/*, audio/*, or video/*)."
            )

        content = model.get("content")
        if not isinstance(content, str):
            raise ValueError(f"File {path!r} did not return base64 content as expected.")
        # Remove any newlines in generated base64 as not all models handle newlines
        content = content.replace("\n", "")

        media_type = mimetype.split("/")[0]
        return MultiModalResponse([{
            "type": media_type,
            "mime_type": mimetype,
            "base64": content,
        }])


# Provided for backwards compatibility
BaseAgent = BeakerAgent

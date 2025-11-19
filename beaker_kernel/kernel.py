import asyncio
import contextvars
import copy
import inspect
import json
import logging
import os
import signal
import sys
import traceback
import uuid
from functools import partial
from typing import Literal, Optional, ClassVar, Awaitable

import requests
from tornado import ioloop

from beaker_kernel.lib.config import reset_config, config
from beaker_kernel.lib.context import BeakerContext, autodiscover_contexts
from beaker_kernel.lib.jupyter_kernel_proxy import InterceptionFilter, JupyterMessage, KernelProxyManager
from beaker_kernel.lib.utils import (message_handler, LogMessageEncoder, magic,
                        handle_message, get_socket, execution_context, parent_message_context,
                        ForwardMessage, ensure_async)

USER_RESPONSE_WAIT_TIME_SECONDS = 100

logger = logging.getLogger(__name__)

MESSAGE_STREAMS = {
    "execute_input": "iopub",
    "execute_request": "shell",
    "execute_result": "iopub",
    "execute_reply": "shell",
    "stream": "iopub",
}

AVAILABLE_CONTEXTS = autodiscover_contexts()


class BeakerKernel(KernelProxyManager):
    implementation: ClassVar[str] = "beaker-kernel"
    implementation_version: ClassVar[str] = "0.1"
    banner: ClassVar[str] = "Beaker Kernel"

    language_info: ClassVar[dict[str, str]] = {
        "mimetype": "text/plain",
        "name": "text",
        "file_extension": ".txt",
    }

    session_config: dict[str, str]
    beaker_session: str
    jupyter_server: Optional[str]
    kernel_id: Optional[str]
    connection_file: Optional[str]
    context: Optional[BeakerContext]
    internal_executions: set[str]
    subkernel_execution_tracking: dict[str, str]
    user_responses: dict[str, str]
    debug_enabled: bool
    magic_commands: dict[str, callable]
    ready: asyncio.Future
    running_actions: dict[str, Awaitable]

    def __init__(self, session_config, kernel_id=None, connection_file=None):
        self.session_config = session_config
        self.beaker_session = session_config.get("beaker_session", None)
        self.jupyter_server = session_config.get("server", config.jupyter_server)
        self.kernel_id = kernel_id
        self.connection_file = connection_file
        self.debug_enabled = False
        self.verbose = False
        self.magic_commands = {}
        self.internal_executions = set()
        self.subkernel_execution_tracking = {}
        self.running_actions = {}
        context_args = session_config.get("context", {})
        super().__init__(session_config, session_id=(self.beaker_session or self.kernel_id))
        self.register_magic_commands()
        self.add_base_intercepts()
        self.context = None
        self.user_responses = dict()
        # Initialize context (Using the event loop to simulate `await`ing the async func in non-async setup)
        event_loop = asyncio.get_event_loop()
        context_task = event_loop.create_task(self.start_default_context(**context_args))
        context_task.add_done_callback(lambda task: None)

    async def start_default_context(self, default_context=None, default_context_payload=None, **options):
        default_context = default_context or os.environ.get('BEAKER_DEFAULT_CONTEXT')
        default_context_payload = default_context_payload or os.environ.get('BEAKER_DEFAULT_CONTEXT_PAYLOAD', "{}")

        # Avoiding passing in optional args so defaults can be used
        optional_args = {}
        language = options.get("language", None) or os.environ.get('BEAKER_DEFAULT_CONTEXT_LANGUAGE', None)
        if language:
            optional_args["language"] = language

        # Set context specific options
        debug = options.get("debug", None) or os.environ.get('BEAKER_DEFAULT_CONTEXT_DEBUG', None)
        verbose = options.get("verbose", None) or os.environ.get('BEAKER_DEFAULT_CONTEXT_VERBOSE', None)
        if debug is not None:
            self.debug_enabled = debug
        if verbose is not None:
            self.verbose = verbose

        if isinstance(default_context_payload, str):
            try:
                default_context_payload = json.loads(default_context_payload)
            except json.JSONDecodeError:
                default_context_payload = {}
        if not default_context:
            sorted_contexts = sorted(autodiscover_contexts().items(), key=lambda item: item[1].WEIGHT)
            first_context = sorted_contexts[0]
            default_context, context_cls = first_context
            default_context_payload = context_cls.default_payload()
        if not default_context:
            default_context = "default"
            default_context_payload = {}
        await self.set_context(default_context, default_context_payload, **optional_args)

    def add_base_intercepts(self):
        """
        Adds intercepts used by the Beaker kernel
        """
        self.server.intercept_message(
            "shell", "context_info_request", self.context_info_request
        )
        self.server.intercept_message(
            "shell", "context_setup_request", self.context_setup_request
        )
        self.server.intercept_message("shell", "llm_request", self.llm_request)
        self.server.intercept_message(
            "shell", "execute_request", self.track_execute_request
        )
        self.server.intercept_message(
            "iopub", "execute_input", self.update_execute_input_response
        )
        self.server.intercept_message("shell", "execute_reply", self.post_execute)
        self.server.intercept_message("stdin", "input_reply", self.input_reply)
        self.server.intercept_message("shell", "set_agent_model", self.set_agent_model)
        self.server.intercept_message("shell", "reset_request", self.reset_kernel)
        self.server.intercept_message("control", "interrupt_request", self.interrupt)
        self.server.intercept_message("control", "shutdown_request", self.shutdown)
        self.server.intercept_message("shell", "notebook_state_response", self.notebook_state_response)
        self.server.intercept_message("shell", "beaker_session_info_request", self.beaker_session_info)

    def register_magic_commands(self):
        for _, method in inspect.getmembers(self, lambda member: inspect.ismethod(member) and hasattr(member, "_magic_prefix")):
            prefix = getattr(method, "_magic_prefix")
            self.magic_commands[prefix] = method

        self.server.intercept_message(
            "shell", "execute_request", self.handle_magic_word
        )

    def api_auth(self) -> str:
        import hashlib
        import time

        preamble = "beaker-kernel"
        nonce = str(int(time.time()))
        kernel_id = self.kernel_id
        key = self.session_config.get("key")

        hash_source = f"{kernel_id}{nonce}{key}".encode()
        hash_value = hashlib.md5(hash_source).hexdigest()

        return f"{preamble}:{kernel_id}:{nonce}:{hash_value}"

    async def handle_magic_word(self, server, target_stream, data):
        message = JupyterMessage.parse(data)
        cell_content: str = message.content.get("code", "").strip()
        if not cell_content.startswith("%"):
            return data
        parts = cell_content.split(maxsplit=1)
        if len(parts) == 1:
            head, tail = parts[0], None
        else:
            head, tail = parts
        for prefix, fn in self.magic_commands.items():
            if head == prefix:
                self.debug(event_type="magic_word", content={"magic_word": head, "fn": fn.__name__})
                async with handle_message(server, target_stream, data) as ctx:
                    with parent_message_context(ctx.message):
                        result = await fn(tail, magic_word=head, parent_header=message.header)
                        ctx.return_val = result
                return None
        return data

    @magic("set_context")
    async def set_context_magic(self, cell_content: str, magic_word=None, parent_header=None):
        context_name, language, context_config = cell_content.split(maxsplit=2)
        context_info = json.loads(context_config)
        self.stdout(f"Switching from context {self.context.slug} to {context_name}...", parent_header=parent_header)
        await self.set_context(context_name=context_name, context_info=context_info, language=language, parent_header=parent_header)

        # Send message to trigger updating the context info
        self.send_response(
            stream="iopub",
            msg_or_type="context_info_update",
            content={},
            parent_header=parent_header,
        )
        self.stdout("Context switch complete.", parent_header=parent_header)

        # TODO: Return the new context info
        return None

    @magic("run_action")
    async def run_action_magic(self, cell_content: str, magic_word=None, parent_header=None):
        action_name, payload = cell_content.split(maxsplit=1)
        request_name = f"{action_name}_request"
        content = json.loads(payload)
        self.stdout(f"Running action `{action_name}`...", parent_header=parent_header)

        for intercept in self.server.filters:
            if intercept.stream_type.name == "shell" and intercept.msg_type == request_name:
                action_func = intercept.callback
                data = self.context.subkernel.connected_kernel.make_multipart_message(msg_type=request_name, content=content, parent_header=parent_header)
                response = await action_func(self.server, self.context.subkernel.connected_kernel.streams.shell, data)
                self.stdout(f"Action `{action_name}` execution complete.", parent_header=parent_header)
                result_data = {}
                try:
                    result_data["text/plain"] = json.dumps(response, cls=LogMessageEncoder, indent=2)
                    result_data["application/json"] = response
                except TypeError:
                    result_data["text/plain"] = str(response)

                self.send_response(
                    stream="iopub",
                    msg_or_type=parent_header.get('msg_type').replace("_request", "") + "_result",
                    content={"execution_count": -1, "data": result_data, "metadata": {}},
                    parent_header=parent_header,
                )
                break
        else:
            self.stderr(f"Unable to find an action with name `{action_name}`.")
        return result_data

    def handle_thoughts(
        self, thought: str, tool_name: str, tool_input: str, parent_header: dict = {}
    ):
        content = {
            "thought": thought,
            "tool_name": tool_name,
            "tool_input": tool_input,
        }
        self.send_response(
            stream="iopub",
            msg_or_type="llm_thought",
            content=content,
            parent_header=parent_header,
        )

    def add_intercept(self, msg_type, func, stream=None):
        if stream is None:
            stream = MESSAGE_STREAMS.get(msg_type, None)
        if stream is None:
            logger.error(
                "No stream found for msg_type=%s.\nNot adding intercept.", msg_type
            )
            return
        self.server.intercept_message(stream, msg_type, func)

    def remove_intercept(self, msg_type, func, stream=None):
        if stream is None:
            stream = MESSAGE_STREAMS.get(msg_type, None)
        if stream is None:
            logger.error(
                "No stream found for msg_type=%s.\nNot able to remove intercept.",
                msg_type,
            )
            return
        socket = get_socket(stream)
        filter = InterceptionFilter(socket, msg_type, func)
        if filter in self.server.filters:
            self.server.filters.remove(filter)

    async def send_preview(self, parent_header=None):
        if self.context.preview:
            with execution_context("preview"):
                preview_payload = await self.context.preview()
                if preview_payload:
                    self.send_response("iopub", "preview", preview_payload, parent_header=parent_header)

    async def send_kernel_state_info(self, parent_header=None):
        if self.context.kernel_state:
            with execution_context("kernel_state_info"):
                state_payload = await self.context.kernel_state()
                if state_payload:
                    self.send_response("iopub", "kernel_state_info", state_payload, parent_header=parent_header)

    async def send_chat_history(self, parent_header=None):
        if self.context.agent.chat_history:
            from archytas.chat_history import OutboundChatHistory, OutboundModel, SummaryRecord, MessageRecord
            from dataclasses import asdict
            chat_history = self.context.agent.chat_history
            model = self.context.agent.model
            records = await chat_history.records(auto_update_context=False)
            output = OutboundChatHistory(
                records=[{
                    "message": {
                        "text": record.message.text,
                        "raw_content": record.message.content,
                        **record.message.model_dump(),
                    },
                    "uuid": record.uuid,
                    "token_count": record.token_count,
                    "metadata": record.metadata,
                    "react_loop_id": record.react_loop_id,
                } for record in records],
                system_message=chat_history.system_message.message.text,
                tool_token_usage_estimate=chat_history.tool_token_estimate,
                model=OutboundModel(
                    provider=model.__class__.__name__,
                    model_name=model.model_name,
                    context_window=model.contextsize()
                ),
                message_token_count=sum(record.token_count for record in records if isinstance(record, MessageRecord) and record.token_count),
                summary_token_count=sum(record.token_count for record in records if isinstance(record, SummaryRecord) and record.token_count),
                overhead_token_count=chat_history.token_overhead,
                summarization_threshold=model.summarization_threshold,
                token_estimate=chat_history._token_estimate or await chat_history.token_estimate(model),
            )
            output_dict = asdict(output)
            self.send_response("iopub", "chat_history", output_dict, parent_header=parent_header)

    async def update_connection_file(self, **kwargs):
        try:
            with open(self.connection_file, "r") as connection_file:
                run_info: dict = json.load(connection_file)
        except IOError:
            run_info = {}
        run_info.update(kwargs)
        with open(self.connection_file, "w") as connection_file:
            json.dump(run_info, connection_file, indent=2)

    async def set_context(self, context_name, context_info, language="python3", subkernel=None, parent_header={}):

        context_cls = AVAILABLE_CONTEXTS.get(context_name, None)
        if not context_cls:
            # TODO: Should we return an error if the requested context isn't available?
            return False

        # Cleanup the old context, then create and setup the new context
        if self.context:
            self.context.cleanup()

        if context_info is None:
            default_payload = context_cls.default_payload()
            if isinstance(default_payload, str):
                default_payload = json.loads(default_payload)
            context_info = default_payload

        context_config = {
            "language": language,
            "subkernel": subkernel,
            "context_info": context_info
        }
        self.context = context_cls(beaker_kernel=self, config=context_config)
        await self.context.setup(context_info=context_info, parent_header=parent_header)
        subkernel = self.context.subkernel
        kernel_setup_func = getattr(subkernel, "setup", None)
        if kernel_setup_func is not None:
            with execution_context(type="setup", name=context_name, parent_header=parent_header):
                await ensure_async(kernel_setup_func())
        await self.update_connection_file(context={"name": context_name, "config": context_info})
        await self.send_preview(parent_header=parent_header)
        await self.send_kernel_state_info(parent_header=parent_header)

    async def post_execute(self, queue, message_id, data):
        message = JupyterMessage.parse(data)

        # Only run if there is an active context
        if self.context is None:
            return data

        # Don't run for internal executions
        if message.parent_header.get("msg_id") in self.internal_executions:
            return data

        # Fetch event loop and ensure it's valid
        loop = asyncio.get_event_loop()
        post_execute = getattr(self.context, "post_execute", None)
        async def task():
            """
            Task that runs post_execute and then preview in the background as a async task.
            This allows the normal execution flow to respond quickly in case these tasks are slow
            or resource intensive.
            """
            coroutines = []
            if post_execute and (callable(post_execute) or inspect.iscoroutinefunction(post_execute)):
                # If we have a callback function, then add it as a task to the execution loop so it runs
                coroutines.append(post_execute(message))
            # Always only generate and send preview after post_execute completes in case state changes or setup is
            # performed in the post_execute function
            coroutines.append(self.send_preview(parent_header=message.parent_header))
            coroutines.append(self.send_kernel_state_info(parent_header=message.parent_header))
            coroutines.append(self.send_chat_history(parent_header=message.parent_header))
            await asyncio.gather(*coroutines)

        if loop:
            loop.create_task(task())
        return data

    def send_response(
        self, stream, msg_or_type, content=None, channel=None, parent_header={}, parent_identities=None, msg_id=None,
    ):
        # Parse response as needed
        stream = getattr(self.server.streams, stream)
        message = self.server.make_multipart_message(
            msg_type=msg_or_type, content=content, parent_header=parent_header, msg_id=msg_id
        )
        if parent_identities:
            stream.send_multipart(parent_identities + message)
        else:
            stream.send_multipart(message)
        # Flush to ensure messages are sent immediately
        # TODO: Make flushing behind a flag?
        stream.flush()
        return message

    async def track_execute_request(self, server, target_stream, data):
        message = JupyterMessage.parse(data)
        if "notebook_item" in message.metadata:
            message_id = message.header["msg_id"]
            notebook_item = message.metadata["notebook_item"]
            self.subkernel_execution_tracking[message_id] = notebook_item
        return data

    async def update_execute_input_response(self, server, target_stream, data):
        message = JupyterMessage.parse(data)
        parent_id = message.parent_header.get("msg_id")
        notebook_item = self.subkernel_execution_tracking.get(parent_id)
        if notebook_item:
            message.metadata["notebook_item"] = notebook_item
            data = message.parts
        return data

    @message_handler
    async def interrupt(self, _message):
        self._interrupt(interrupt_subkernel=True)

    def soft_interrupt(self, signal, frame):
        self._interrupt(interrupt_subkernel=False)

    def _interrupt(self, interrupt_subkernel=True):
        if interrupt_subkernel:
            try:
                subkernel_id = self.context.subkernel.kernel_id
                print(f"Interrupting connected subkernel: {subkernel_id}")
                requests.post(
                    f"{self.context.beaker_kernel.jupyter_server}/api/kernels/{subkernel_id}/interrupt",
                    headers={"Authorization": f"token {config.jupyter_token}"},
                    timeout=0.5,
                )
            except requests.exceptions.HTTPError as err:
                logger.error(f"Subkernel cannot be interrupted.\nDetails:\n  {err.request.body}", exc_info=err)
            except requests.exceptions.ConnectionError:
                logger.error(f"Subkernel cannot be interrupted.\nDetails:\n  {err}", exc_info=err)

        for key, value in list(self.running_actions.items()):
            if inspect.iscoroutine(value):
                value.throw(asyncio.CancelledError, "Execution interrupted by user.")
            elif isinstance(value, asyncio.Future):
                value.cancel(msg="Execution interrupted by user.")
            del self.running_actions[key]
        return None

    @message_handler
    async def shutdown(self, message):
        def stop_loop(loop: ioloop.IOLoop):
            loop.stop()
        self.context.cleanup()
        self.context = None
        # Stop loop after short delay to allow cleanup to run.
        loop = ioloop.IOLoop.current()
        loop.call_later(0.2, stop_loop, loop)
        return None

    async def prompt_user(self, query, parent_message=None, format: Optional[Literal['workflow_confirmation']]=None):
        msg_id = str(uuid.uuid4())
        self.send_response(
            "stdin",
            "input_request",
            {"prompt": query, "format": format},
            parent_header=getattr(parent_message, "header", None),
            parent_identities=getattr(parent_message, "identities", None),
            msg_id=msg_id,
        )
        sleep_duration = 0.2
        for _ in range(round(USER_RESPONSE_WAIT_TIME_SECONDS / sleep_duration)):
            if msg_id in self.user_responses:
                result = self.user_responses[msg_id]
                del self.user_responses[msg_id]
                return result
            await asyncio.sleep(sleep_duration)

        raise Exception("Query timed out. User took too long to respond.")

    def log(self, event_type: str, content, parent_header=None):
        # Re-encode data to fix issues with un-json-encodable elements in the debug output
        content = json.loads(json.dumps(content, cls=LogMessageEncoder))
        message_content = {
            "seq": 0,
            "type": "event",
            "event": event_type,
            "body": content,
        }
        message = self.server.make_multipart_message(
            msg_type="debug_event",
            content=message_content,
            parent_header=parent_header,
        )
        stream = self.server.streams.iopub
        stream.send_multipart(message)
        stream.flush()

    def debug(self, event_type: str, content, parent_header=None):
        if not self.debug_enabled:
            return
        self.log(event_type=event_type, content=content, parent_header=parent_header)

    def send_stream_message(self, stream_type, text, parent_header=None):
        if isinstance(text, bytes):
            text = text.decode()
        message = self.server.make_multipart_message(
            msg_type="stream",
            content={
                'name': stream_type,
                'text': text,
            },
            parent_header=parent_header,
        )
        stream = self.server.streams.iopub
        stream.send_multipart(message)
        stream.flush()

    def stdout(self, text, parent_header=None):
        self.send_stream_message(stream_type="stdout", text=text, parent_header=parent_header)

    def stderr(self, text, parent_header=None):
        self.send_stream_message(stream_type="stderr", text=text, parent_header=parent_header)

    @message_handler
    async def llm_request(self, message: JupyterMessage):
        from archytas.exceptions import AuthenticationError
        content: dict = message.content
        request = content.get("request", None)
        if not request:
            return
        if not self.context:
            raise Exception("Context has not been set")
        setattr(self.context, "current_llm_query", request)

        notebook_state = message.metadata.get("notebook_state", None)
        if notebook_state is not None:
            self.context.notebook_state = notebook_state

        request_key = f"llm_query:{message.header['msg_id']}"
        try:
            try:
                # Before starting ReAct loop, replace thought handler with partial func with parent_header so we can track
                # thoughts
                if self.context.agent:
                    self.context.agent.thought_handler = partial(self.handle_thoughts, parent_header=message.header)
                self.debug("llm_query", request, parent_header=message.header)
                task = asyncio.create_task(self.context.agent.react_async(request, react_context={"message": message}))
                self.running_actions[request_key] = task
                result = await task
            except AuthenticationError as err:
                self.send_response(
                    stream="iopub",
                    msg_or_type="llm_auth_failure",
                    content={
                        "msg": str(err),
                    },
                    parent_header=message.header,
                )
                return
            except asyncio.CancelledError as err:
                self.send_response(
                    stream="iopub",
                    msg_or_type="stream",
                    content={
                        "name": "stderr",
                        "text": "Request interrupted.",
                    },
                    parent_header=message.header,
                )
                raise
            except Exception as err:
                error_text = f"""LLM Error:
    {err}

    {traceback.format_exc()}
    """
                stream_content = {"name": "stderr", "text": error_text}
                self.send_response(
                    "iopub", "stream", stream_content, parent_header=message.header
                )
                raise
            try:
                # Normalize result
                if isinstance(result, (str, bytes, bytearray)):
                    data = json.loads(result)
                else:
                    data = result

                if isinstance(data, dict) and data.get("action") == "code_cell":
                    stream_content = {
                        "language": data.get("language"),
                        "code": data.get("content"),
                    }
                    self.send_response(
                        "iopub", "code_cell", stream_content, parent_header=message.header
                    )
                else:
                    stream_content = {"name": "response_text", "text": f"{data}"}
                    self.send_response(
                        "iopub", "llm_response", stream_content, parent_header=message.header
                    )
            except (
                json.JSONDecodeError
            ):  # If response is not a json, it's just text so treat it like text
                stream_content = {"name": "response_text", "text": f"{result}"}
                self.send_response(
                    "iopub", "llm_response", stream_content, parent_header=message.header
                )
            finally:
                # When done, put thought handler back to default to not potentially cause confused thoughts.
                self.context.agent.thought_handler = self.handle_thoughts
                setattr(self.context, "current_llm_query", None)
        finally:
            if request_key in self.running_actions:
                del self.running_actions[request_key]
        await self.send_chat_history(message.header)

    @message_handler
    async def context_info_request(self, message):
        if self.context is not None:
            context_slugs_by_class = dict((cls, slug) for slug, cls in AVAILABLE_CONTEXTS.items())
            context_class = self.context.__class__
            context_slug = context_slugs_by_class.get(context_class, "Not Found")
            full_context_class = f"{context_class.__module__}.{context_class.__name__}"
            context_config = getattr(self.context, "config", {}).get("context_info", None)
            context_info = await self.context.get_info()
            language_slug = self.context.subkernel.SLUG
            subkernel_name = self.context.subkernel.KERNEL_NAME
        else:
            context_slug = "NONE"
            full_context_class = "None"
            context_config = None
            language_slug = "Not set"
            subkernel_name = "Not set"
            context_info = None

        self.send_response(
            stream="iopub",
            msg_or_type="context_info_response",
            content={
                "slug": context_slug,
                "class": full_context_class,
                "config": context_config,
                "language": {
                    "slug": language_slug,
                    "subkernel": subkernel_name,
                },
                "info": context_info,
            },
            parent_header=message.header,
        )
        await self.send_chat_history(message.header)
        return None

    @message_handler
    async def context_setup_request(self, message):
        content = message.content
        context_name = content.get("context")
        context_info = content.get("context_info", {})
        language = content.get("language", "python3")
        subkernel = content.get("subkernel", None)
        enable_debug = content.get("debug", None)
        verbose = content.get("verbose", None)

        # Only update enable_debug and verbose if they are set and valid types.
        if verbose in (True, False):
            self.verbose = verbose
        if enable_debug in (True, False):
            self.debug_enabled = enable_debug
        if enable_debug in (True, False) or verbose in (True, False):
            self.debug("debug_update", {"debug_enabled": self.debug_enabled, "verbose": self.verbose}, parent_header=message.header)

        parent_header = copy.deepcopy(message.header)
        if content:
            await self.set_context(
                context_name,
                context_info,
                language=language,
                subkernel=subkernel,
                parent_header=parent_header
            )

        # Send context_response
        context_response_content = await self.context.get_info()
        self.send_response(
            stream="iopub",
            msg_or_type="context_setup_response",
            content=context_response_content,
            parent_header=parent_header,
        )

    @message_handler(send_status_updates=False, send_reply=False)
    async def input_reply(self, message):
        content = message.content
        parent_id = message.parent_header["msg_id"]
        self.user_responses[parent_id] = content["value"]

    @message_handler
    async def set_agent_model(self, message):
        provider_id = message.content.get("provider_id", None)
        model_config = message.content.get("model_config", None)
        if provider_id or model_config:
            model = config.get_model(provider_id=provider_id, model_config=model_config)
        else:
            # Refresh the cached config object so we pick up any changes to the config at the source
            reset_config()
            model = config.get_model()
        if model:
            self.context.agent.model = model
        await self.send_chat_history(message.header)

    @message_handler
    async def reset_kernel(self, message):
        reset_config()
        await self.set_context(
            self.context.SLUG,
            self.context.config,
            language=self.context.subkernel.SLUG,
            parent_header=message.header
        )
        await self.send_chat_history(message.header)
        return True

    @message_handler
    async def beaker_session_info(self, message):
        return await self.context.get_info()

    async def notebook_state_response(self, server, target_stream, data):
        async with handle_message(server, target_stream, data, send_status_updates=False, send_reply=False) as ctx:
            setattr(self.notebook_state_response.__func__, 'result', ctx.message.content)
            return None
    setattr(notebook_state_response, 'result', None)

    async def request_notebook_state(self, parent_message=None):
        msg_id = str(uuid.uuid4())
        self.send_response(
            "iopub",
            "notebook_state_request",
            {},
            parent_header=getattr(parent_message, "header", None),
            parent_identities=getattr(parent_message, "identities", None),
            msg_id=msg_id,
        )
        timeout = 1
        steps = 10
        sleep_duration = timeout / steps
        for _ in range(steps):
            result = getattr(self.notebook_state_response, 'result', None)
            if result != None:
                setattr(self.notebook_state_response.__func__, 'result', None)
                return result
            await asyncio.sleep(sleep_duration)
        return None


# Provided for backwards compatibility
LLMKernel = BeakerKernel


def cleanup(kernel: BeakerKernel):
    try:
        if kernel.context is not None:
            kernel.context.cleanup()
    except requests.exceptions.ConnectionError:
        print("Unable to connect to server. Possible server shutdown.")
    except Exception as err:
        print(f"Error during cleanup: {err}")
        traceback.print_exc()


def start(connection_file):
    loop = ioloop.IOLoop.current()

    with open(connection_file) as f:
        notebook_config = json.load(f)

    _, kernel_file = os.path.split(connection_file)
    kernel_id = os.path.basename(kernel_file)[7:-5]  # Remove 'kernel-' and '.json' from the beginning and end of the filename.
    kernel = BeakerKernel(notebook_config, kernel_id=kernel_id, connection_file=connection_file)

    try:
        # Catch INTERRUPT signals and treat them as soft interrupts.
        signal.signal(signal.SIGINT, kernel.soft_interrupt)
        loop.start()
    finally:
        # Perform shutdown cleanup here
        cleanup(kernel)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        sys.exit(0)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "start":
        start(sys.argv[2])
    else:
        print("Usage: {:s} start <connection_file>".format(sys.argv[0]))


if __name__ == "__main__":
    main()

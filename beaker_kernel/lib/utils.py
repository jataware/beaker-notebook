import asyncio
import contextvars
import os
import inspect
import json
import logging
import re
import sys
import traceback
import typing
import warnings
from frozendict import frozendict
from collections import namedtuple
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from functools import wraps, update_wrapper
from importlib import import_module
from pathlib import Path
from typing import Any, TYPE_CHECKING, Callable, List, Coroutine

from archytas.models.base import BaseArchytasModel
from archytas.exceptions import AuthenticationError

from .jupyter_kernel_proxy import ( KERNEL_SOCKETS, KERNEL_SOCKETS_NAMES,
                                   JupyterMessage, JupyterMessageTuple)


BeakerEntryPoint = namedtuple("BeakerEntryPoint", ("type", "import_string"))

logger = logging.getLogger(__name__)

execution_context_var = contextvars.ContextVar('execution_context', default=None)
parent_message_var = contextvars.ContextVar('parent_message_var', default={})

class ForwardMessage: pass

def env_enabled(env_var: str):
    return os.environ.get(env_var, "false").lower() == "true"

def get_socket(stream_name: str):
    socket = KERNEL_SOCKETS[KERNEL_SOCKETS_NAMES.index(stream_name)]
    return socket

def import_dotted_class(import_string: str):
    try:
        module_name, class_name = import_string.rsplit('.', 1)
    except Exception as err:
        raise
    module = import_module(module_name)
    cls = getattr(module, class_name, None)
    return cls

def find_file_along_path(filename: str, start_path: Path | str | None = None) -> Path | None:
    if start_path is None:
        path = Path.cwd()
    else:
        path = Path(start_path)
    for search_path in [path, *path.parents]:
        potential_file = search_path / filename
        if potential_file.is_file():
            return potential_file
    return None

class DefaultModel(BaseArchytasModel):
    def initialize_model(self, **kwargs):
        return

    def invoke(self, input, *, config=None, stop=None, **kwargs):
        raise AuthenticationError("Model not found or misconfigured. Please check your provider configuration.")

    def ainvoke(self, input, *, config=None, stop=None, **kwargs):
        raise AuthenticationError("Model not found or misconfigured. Please check your provider configuration.")

class ExecutionError(RuntimeError):
    def __init__(self, ename: str, evalue: str, traceback: List[str]) -> None:
        super().__init__(ename, evalue, traceback)

class ExecutionTask(asyncio.Task):
    execute_request_msg: JupyterMessage | None

    def __init__(
        self,
        *args,
        execute_request_msg: JupyterMessage | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.execute_request_msg = execute_request_msg


class handle_message(AbstractAsyncContextManager):
    def __init__(self, server, target_stream, msg_data: JupyterMessageTuple, send_status_updates=True, send_reply=True) -> None:
        super().__init__()
        self.beaker_kernel = server.manager
        self.send_status_updates = send_status_updates
        self.send_reply = send_reply
        message = JupyterMessage.parse(msg_data)
        self.server = server
        self.target_stream = target_stream
        self.msg_data = msg_data
        self.message = message
        self.message_type = message.header["msg_type"]
        self.reply_type = self.message_type.replace("_request", "") + "_reply"
        self.return_val = None
        if self.send_status_updates:
            self.beaker_kernel.send_response(
                "iopub", "status", {"execution_state": "busy"}, parent_header=message.header
            )

    async def __aenter__(self):
        """Return `self` upon entering the runtime context."""
        return self

    async def __aexit__(self, exc_type, exc_value, traceback_value):
        """Raise any exception triggered within the runtime context."""
        match exc_type:
            case asyncio.CancelledError():
                reply_content = {
                    "status": "aborted",
                    "execution_count": None,
                }
            case BaseException():
                formatted_tb = traceback.format_exception(exc_type, exc_value, traceback_value)
                sys.stderr.write("\n".join(formatted_tb))
                sys.stderr.flush()
                reply_content = {
                    "status": "error",
                    "execution_count": None,
                    "ename": exc_type.__name__,
                    "evalue": str(exc_value),
                    "traceback": formatted_tb,
                }
            case _:
                reply_content = {
                    "status": "ok",
                    "execution_count": None,
                    "return": self.return_val,
                }

        if self.send_reply:
            self.beaker_kernel.send_response(
                "shell", self.reply_type, reply_content, parent_header=self.message.header, parent_identities=self.message.identities
            )
        if self.send_status_updates:
            self.beaker_kernel.send_response(
                "iopub", "status", {"execution_state": "idle"}, parent_header=self.message.header, parent_identities=self.message.identities
            )
        return None


def message_handler(func=None, /, *, send_status_updates=True, send_reply=True) -> None:
    """
    Method decorator that handles the parsing and responding to of messages.
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(self, server, target_stream, data: JupyterMessageTuple):
            async with handle_message(server, target_stream, data, send_status_updates=send_status_updates, send_reply=send_reply) as ctx:
                with parent_message_context(ctx.message):
                    result = await fn(self, ctx.message)
                    # If message data is returned, then the message should be proxied, but if None or any other type is
                    # returned, the message should be dropped and not continue on to the proxied server.
                    match result:
                        case JupyterMessage():
                            ctx.send_reply = False
                            return result.parts
                        case ForwardMessage():
                            ctx.send_reply = False
                            return data
                        case _:
                            ctx.return_val = result
                            return None
        return wrapper

    if func is not None:
        return decorator(func)
    else:
        return decorator


def intercept(msg_type=None, stream="shell", docs: str|None=None, default_payload=None):
    """
    Method decorator to identify message intercepts.
    """
    def register_intercept(fn):
        # Wrap function in message_handler decorator/wrapper for that functionality, which we always want.
        fn = message_handler(fn)
        message_type = msg_type or fn.__name__  # Default msg_type value to be the name of the function if undefined/falsey
        setattr(fn, "_intercept", (message_type, stream))

        fn_docs = getattr(fn, "_docs", getattr(fn, "__doc__", None))
        if docs is not None:
            setattr(fn, "_docs", docs.strip())
        else:
            if isinstance(fn_docs, str):
                setattr(fn, "_docs", fn_docs.strip())
            else:
                setattr(fn, "_docs", fn_docs)

        if default_payload is not None:
            setattr(fn, "_default_payload", default_payload)

        update_wrapper(register_intercept, fn)
        return fn

    return register_intercept


def action(action_name: str|None=None, docs: str|None=None, default_payload=None, enabled: None|Callable[[], bool]=None, scope: typing.Literal["internal", "external", "global"]="global"):
    """
    Method decorator to identify and register context actions.
    """
    if enabled is not None and not enabled():
        def disable(_fn):
            def disabled_message(*args, **kwargs):
                raise RuntimeError("This action is disabled.")
            return disabled_message
        return disable
    def register_method(fn):

        action_nm = action_name or fn.__name__  # Default msg_type value to be the name of the function if undefined/falsey
        if action_nm.lower().endswith("request"):
            logger.error("Beaker action names should not include the `_request` suffix.")
        msg_request_type = f"{action_nm}_request"

        setattr(fn, "_action", action_nm)
        setattr(fn, "_scope", scope)

        if default_payload and hasattr(fn, '_default_payload') and default_payload != getattr(fn, '_default_payload'):
            raise ValueError(f"The default payload for action `{action_nm}` is defined twice. Please ensure only one definition.")

        @wraps(fn)
        async def with_context(self, message):
            with execution_context("action", action_nm):
                return await ensure_async(fn(self, message))

        intercept_fn = intercept(msg_type=msg_request_type, stream="shell", docs=docs, default_payload=default_payload)(with_context)
        update_wrapper(register_method, intercept_fn)
        return intercept_fn
    return register_method


def magic(magic_word: str|None):
    """
    Method decorator to identify magic word action methods
    """
    def register_magic(fn):
        magic_prefix = "%" + (magic_word or fn.__name__)
        setattr(fn, "_magic_prefix", magic_prefix)
        update_wrapper(register_magic, fn)
        return fn
    return register_magic


class LogMessageEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        try:
            return super().default(o)
        except:
            return str(o)


class SubkernelStateEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        # if callable(o):
        #     # return f"Function named"
        #     return super().default(o)
        try:
            return super().default(o)
        except:
            return str(o)


def togglable_tool(env_var, *, name: str | None = None):
    warnings.warn("This decorator is deprecated and will be removed in version 1.6.0")
    def noop(fn):
        return fn
    return noop


class execution_context(AbstractContextManager):
    def __init__(self, type=None, name=None, **extra) -> None:
        self.token = None
        self.type = type
        self.name = name
        self.extra = extra

    def __enter__(self) -> Any:
        self.token = execution_context_var.set(frozendict({
            "type": self.type,
            "name": self.name,
            **self.extra
        }))
        return super().__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        execution_context_var.reset(self.token)
        return super().__exit__(exc_type, exc_value, traceback)

def get_execution_context():
    context = execution_context_var.get()
    return context

class parent_message_context(AbstractContextManager):
    def __init__(self, parent_message={}, **extra) -> None:
        self.token = None
        self.parent_message = parent_message
        self.extra = extra

    def __enter__(self) -> Any:
        context = {
            "parent_message": self.parent_message,
            **self.extra,
        }
        self.token = parent_message_var.set(frozendict(context))
        return super().__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        parent_message_var.reset(self.token)
        return super().__exit__(exc_type, exc_value, traceback)

def get_parent_message():
    context = parent_message_var.get()
    return context


def set_tool_execution_context(fn):
    tool_name = getattr(fn, '_name', None)
    if not getattr(fn, '_is_tool', False) or not tool_name:
        return fn
    run_fn = getattr(fn, 'run')
    if run_fn:
        @wraps(run_fn)
        async def with_context(*args, **kwargs):
            with execution_context(type="tool", name=tool_name):
                return await ensure_async(run_fn(*args, **kwargs))

        fn.__dict__['run'] = with_context


async def ensure_async(fn: Coroutine|Callable):
    if inspect.iscoroutine(fn) or inspect.iscoroutinefunction(fn):
        return await fn
    else:
        return fn

def slugify(name: str):
    slug = "_".join(re.split(r"\W", name.lower().strip()))
    return slug

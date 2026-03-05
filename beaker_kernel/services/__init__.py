import json
import typing
from dataclasses import is_dataclass, asdict
from typing import ClassVar, Optional, Any

from tornado.web import HTTPError

from jupyter_client.jsonutil import json_default as jupyter_json_default
from jupyter_server.base.handlers import JupyterHandler


# Core business logic services
from .session import BeakerSessionManager

__all__ = [
    "BeakerSessionManager",
    "HTTPError",
    "ServiceApi",
    "ServiceApiHandler",
]


def json_default(obj: typing.Any) -> typing.Any:
    if isinstance(obj, type):
        return f"{obj.__module__}.{obj.__name__}"
    return jupyter_json_default(obj)


class ServiceApi:
    prefix: ClassVar[str]
    handlers: ClassVar[list[tuple[str, type[JupyterHandler], *tuple[Any, ...]]]]

    def __init_subclass__(cls):
        cls.handlers = []
        for member in cls.__dict__.values():
            if isinstance(member, type) and issubclass(member, ServiceApiHandler):
                handler: type[ServiceApiHandler] = member
                path = fr"/beaker/{cls.prefix}/?{handler.pattern}$"
                extra = getattr(handler, "extra", None)
                if callable(extra):
                    extra = extra()
                args = [extra] if extra is not None else []
                cls.handlers.append((path, handler, *args))


class ServiceApiHandler(JupyterHandler):
    pattern: ClassVar[Optional[str]]

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json")

    def write(self, chunk):
        if is_dataclass(chunk):
            chunk = asdict(chunk)
        elif isinstance(chunk, list):
            chunk = [asdict(item) if is_dataclass(item) else item for item in chunk]
        if isinstance(chunk, (dict, list)):
            chunk = json.dumps(chunk, default=json_default)
        return super().write(chunk)

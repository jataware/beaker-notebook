import importlib
import logging
import os
import sys
import urllib.parse
from typing import get_origin, get_args
from dataclasses import is_dataclass, asdict
from typing import TYPE_CHECKING, get_origin, get_args, GenericAlias, Union, Generic, Generator, Optional, Any


from beaker_kernel.lib.autodiscovery import autodiscover
from beaker_kernel.lib.app import BeakerApp
from beaker_kernel.lib.context import BeakerContext
from beaker_kernel.lib.subkernel import BeakerSubkernel
from beaker_kernel.lib.agent_tasks import summarize
from beaker_kernel.lib.config import config, locate_config, Config, Table, Choice, recursiveOptionalUpdate, reset_config
from beaker_kernel.service import admin_utils

if TYPE_CHECKING:
    from beaker_kernel.service.base import BaseBeakerApp

logger = logging.getLogger(__name__)

PREFIX = '/beaker/'

def find_api_handlers(base=None) -> Generator[tuple[str, Any, str], None, None]:
    """Discover and yield API handlers from registered Beaker extensions.

    This function uses the Beaker extension autodiscovery mechanism to find
    all extensions that may provide API handlers. It then iterates through
    each extension's handlers and yields them one by one.

    Yields
    ------
    tuple[str, Any, str]
        A tuple containing the URL pattern, handler class, and optional name
        for each discovered API handler.
    """
    if base is None:
        package = __package__
        base_dir = os.path.dirname(sys.modules[package].__file__)
    else:
        match base:
            case str():
                if os.path.pathsep in base:
                    base_dir = base
                else:
                    try:
                        mod = importlib.import_module(base)
                        base_dir = os.path.dirname(mod.__file__)
                    except ImportError:
                        logger.error(f"Could not import module {base} for API handler discovery")
                        return
            case os.PathLike():
                base_dir = os.fspath(base)
            case _:
                logger.error(f"Invalid base parameter type: {type(base)}")
                return

    for f in os.listdir(base_dir):
        if f.endswith('.py') and f != '__init__.py' and f != 'handlers.py':
            s = f'beaker_kernel.service.api.{f[:-3]}'
            mod = importlib.import_module(s)
            if "handlers" in dir(mod):
                logger.warning(f"Found handlers in {s}")
                for handlers in getattr(mod, "handlers"):
                    yield handlers


def add_handler_prefix(prefix: str, handler_tuple: tuple[str]):
    path, rest = handler_tuple[0], handler_tuple[1:]
    if not prefix.endswith('/'):
        prefix = prefix + '/'
    if path.startswith('/'):
        path = path.lstrip('/')
    return (urllib.parse.urljoin(prefix, path), *rest)


def register_api_handlers(app: "BaseBeakerApp"):
    app.handlers.extend([
        add_handler_prefix(PREFIX, handler)
        for handler in find_api_handlers()
    ])

import asyncio
import importlib
import json
import logging
import os
import traceback
import uuid
import urllib.parse
from typing import get_origin, get_args
from dataclasses import is_dataclass, asdict
from collections.abc import Mapping, Collection
from pathlib import Path
from typing import get_origin, get_args, GenericAlias, Union, Generic, Generator, Optional
from types import UnionType

from jupyter_server.auth.decorator import authorized
from jupyter_server.base.handlers import JupyterHandler
from jupyter_server.extension.handler import ExtensionHandlerMixin
from jupyterlab_server import LabServerApp
from tornado import web, httputil
from tornado.web import StaticFileHandler, RedirectHandler, RequestHandler, HTTPError

from beaker_kernel.lib.autodiscovery import autodiscover
from beaker_kernel.lib.app import BeakerApp
from beaker_kernel.lib.context import BeakerContext
from beaker_kernel.lib.subkernel import BeakerSubkernel
from beaker_kernel.lib.agent_tasks import summarize
from beaker_kernel.lib.config import config, locate_config, Config, Table, Choice, recursiveOptionalUpdate, reset_config
from beaker_kernel.service import admin_utils
from .api.handlers import register_api_handlers

logger = logging.getLogger(__name__)

def sanitize_env(env: dict[str, str]) -> dict[str, str]:
    # Whitelist must match the env variable name exactly and is checked first.
    # Blacklist can match any part of the variable name.
    WHITELIST = ["JUPYTER_TOKEN",]
    BLACKLIST = ["KEY", "SECRET", "TOKEN", "PASSWORD"]
    safe_env = {}
    for env_name, env_value in env.items():
        if env_name in WHITELIST or not any([unsafe_word.upper() in env_name.upper() for unsafe_word in BLACKLIST]):
            safe_env[env_name] = env_value
    return safe_env


def request_log_handler(handler: JupyterHandler):
    """Allow for debugging/extra logging of requests"""
    SKIPPED_METHODS = [
        "OPTIONS",
    ]
    logger: logging.Logger|None = None
    if hasattr(handler, "log"):
        logger = handler.log
    elif hasattr(handler, "settings") and "serverapp" in handler.settings:
        logger = logging.getLogger(handler.settings["serverapp"].__class__.__name__)
    else:
        logger = logging.getLogger(__file__)

    request_time = 1000.0 * handler.request.request_time()
    method = handler.request.method.upper()
    if method in SKIPPED_METHODS:
        return
    logger.info(
        "%d %s %.2fms",
        handler.get_status(),
        handler._request_summary(),
        request_time,
    )


class PageHandler(StaticFileHandler):
    """
    Special handler that
    """
    async def get(self, path: str, include_body: bool = True) -> None:

        # Always serve index.html as routing is performed in app.
        absolute_path = self.get_absolute_path(self.root, "index.html")
        try:
            validated_path = self.validate_absolute_path(self.root, absolute_path)
        except HTTPError as e:
            # If path cannot be found, check again with a .html extension
            if e.status_code == 404:
                html_path = f"{absolute_path}.html"
                validated_path = self.validate_absolute_path(self.root, html_path)
            else:
                raise

        # If no session is provided on a root request, generate a session uuid and redirect to it
        session_id = self.get_query_argument("session", None)
        if not session_id:
            session_id = str(uuid.uuid4())
            to_url = httputil.url_concat(
                f"{'/' if path.startswith('/') else '' }{path}",
                {"session": session_id},
            )
            return self.redirect(to_url, permanent=False)
        path = os.path.relpath(validated_path, self.root)
        self.absolute_path = validated_path

        # Ensure a proper xsrf cookie value is set.
        cookie_name = self.settings.get("xsrf_cookie_name", "_xsrf")
        xsrf_token = self.xsrf_token.decode("utf8")
        xsrf_cookie = self.request.cookies.get(cookie_name, None)
        if not xsrf_cookie or xsrf_cookie.value != xsrf_token:
            kwargs = self.settings.get("xsrf_cookie_kwargs", {})
            self.set_cookie(cookie_name, xsrf_token, **kwargs)

        return await super().get(path, include_body=include_body)


class ConfigController(ExtensionHandlerMixin, JupyterHandler):
    """
    """
    @staticmethod
    def map_type(type_obj: type):
        type_def = {}
        try:
            try:
                type_origin = get_origin(type_obj)
                type_args = get_args(type_obj)
            except:
                type_origin = None
                type_args = None
            if type_args:
                if isinstance(type_obj, UnionType):
                    type_def["type_str"] = repr(type_obj)
                elif issubclass(type_origin, Choice):
                    source = get_args(type_args[0])[0]
                    type_def["type_str"] = f"{type_origin.__name__}['{source}']"
                    type_def["choice_source"] = source
                else:
                    type_def["type_str"] = f"{type_origin.__name__}[{', '.join(arg.__name__ for arg in type_args)}]"
                if type_origin:
                    type_def["type_origin"] = ConfigController.map_type(type_origin)
                if type_args:
                    type_def["type_args"] = [ConfigController.map_type(type_arg) for type_arg in type_args]

            elif is_dataclass(type_obj):
                type_def.update(ConfigController.jsonify_dataclass_schema(type_obj))
            else:
                if isinstance(type_obj, type):
                    type_def["type_str"] = type_obj.__name__
                else:
                    type_def["type_str"] = repr(type_obj)

            if hasattr(type_obj, "default_value"):
                default_value = type_obj.default_value()
                type_def["default_value"] = default_value
            else:
                try:
                    default_value = type_obj()
                    type_def["default_value"] = default_value
                except TypeError:
                    pass
        except:
            type_def["type_str"] = repr(type_obj)
        return type_def


    @staticmethod
    def jsonify_dataclass_schema(obj):
        result = {
            "type_str": f"Dataclass[{obj.__name__}]",
            "fields": {},
        }
        for field_name, field in obj.__dataclass_fields__.items():
            type_def = ConfigController.map_type(field.type)
            metadata = dict(field.metadata)
            description = metadata.pop("description", None)
            option_func = metadata.pop("options", None)
            if option_func and callable(option_func):
                metadata["options"] = option_func()
            field_result = {
                "name": field.name,
                "description": description,
                "metadata": metadata,
                **type_def,
            }
            result["fields"][field_name] = field_result

        return result


    @staticmethod
    def jsonify_dataclass_object(obj):
        result = {}
        for field_name, field in obj.__dataclass_fields__.items():
            current_value = getattr(obj, field_name, None)
            if get_origin(field.type) and issubclass(get_origin(field.type), Table):
                record_type = get_args(field.type)[0]
                if is_dataclass(record_type):
                    current_value = {
                        key: ConfigController.jsonify_dataclass_object(record_type(**value))
                        for key, value in current_value.items()
                    }
            # TODO: Verify value is in choice list?
            # elif get_origin(field.type) and issubclass(get_origin(field.type), Choice):
            #     current_value = ""
            elif is_dataclass(current_value):
                current_value = ConfigController.jsonify_dataclass_object(current_value)
                if not current_value:
                    current_value = {}

            if field.metadata.get("sensitive", True):
                # Track if a value is defined or not.
                current_value = None if current_value else ""
                # current_value = ""
            result[field_name] = current_value
        return result


    def get(self):
        if "schema" in self.request.query:
            return self.get_config_schema()
        else:
            return self.get_config()

    async def post(self):
        config_changes = self.get_json_body()
        updated_config: dict = recursiveOptionalUpdate(config, config_changes)
        config.update(updates=updated_config)
        reset_config()
        return await self.get_config()

    async def get_config_schema(self):
        config_cls = Config
        schema = self.jsonify_dataclass_schema(config_cls)
        return self.write(schema)


    async def get_config(self):
        config_file = locate_config()
        payload = self.jsonify_dataclass_object(config)

        return self.write(
            {
                "config": payload,
                "config_type": config.config_type,
                "config_id": str(config_file),
            }
        )

class ConfigHandler(ExtensionHandlerMixin, JupyterHandler):
    """
    Provide config via an endpoint
    """

    def get(self):
        # If BASE_URL is not provided in the environment, assume that the base url is the same location that
        # is handling this request, as reported by the request headers.
        # If APP_URL is not provided, assume it is the same as BASE_URL.

        base_url = os.environ.get("JUPYTER_BASE_URL", f"{self.request.protocol}://{self.request.host}")

        base_scheme = urllib.parse.urlparse(base_url).scheme
        if base_scheme.endswith("s"):
            ws_scheme = "wss"
        else:
            ws_scheme = "ws"
        ws_url = base_url.replace(base_scheme, ws_scheme)

        extension_config = self.extensionapp.extension_config
        beaker_app: BeakerApp|None = extension_config.get("app", None)

        config_data = {
            # "appendToken": True,
            "appUrl": os.environ.get("APP_URL", base_url),
            "baseUrl": base_url,
            "wsUrl": os.environ.get("JUPYTER_WS_URL", ws_url),
            "token": config.jupyter_token,
            "config_type": config.config_type,
            "extra": {}
        }
        if hasattr(config, "send_notebook_state"):
            config_data["extra"]["send_notebook_state"] = config.send_notebook_state
        if beaker_app:
            config_data["appConfig"] = beaker_app.as_dict()

        # Ensure a proper xsrf cookie value is set.
        cookie_name = self.settings.get("xsrf_cookie_name", "_xsrf")
        xsrf_token = self.xsrf_token.decode("utf8")
        xsrf_cookie = self.request.cookies.get(cookie_name, None)
        if not xsrf_cookie or xsrf_cookie.value != xsrf_token:
            kwargs = self.settings.get("xsrf_cookie_kwargs", {})
            self.set_cookie(cookie_name, xsrf_token, **kwargs)

        return self.write(config_data)


class ContextHandler(ExtensionHandlerMixin, JupyterHandler):
    """
    Provide information about llm contexts via an endpoint
    """

    def get(self):
        """Get the main page for the application's interface."""
        ksm = self.kernel_spec_manager
        contexts: dict[str, BeakerContext] = autodiscover("contexts")
        possible_subkernels: dict[str, BeakerSubkernel] = autodiscover("subkernels")
        subkernel_by_kernel_index = {subkernel.KERNEL_NAME: subkernel for subkernel in possible_subkernels.values()}
        installed_kernels = [
            subkernel_by_kernel_index[kernel_name] for kernel_name in ksm.find_kernel_specs().keys()
            if kernel_name in subkernel_by_kernel_index
        ]
        contexts = sorted(contexts.items(), key=lambda item: (item[1].WEIGHT, item[0]))

        # Extract data from auto-discovered contexts and subkernels to provide options
        context_data = {
            context_slug: {
                "languages": [
                    {
                        "slug": subkernel_slug,
                        "subkernel": getattr(possible_subkernels.get(subkernel_slug), "KERNEL_NAME")
                    }
                    for subkernel_slug in context.available_subkernels()
                    if subkernel_slug in set(subkernel.SLUG for subkernel in installed_kernels)
                ],
                "defaultPayload": context.default_payload()
            }
            for context_slug, context in contexts
        }
        return self.write(context_data)


class DownloadHandler(RequestHandler):
    def get(self, filepath: str):
        if filepath.startswith("."):
            raise HTTPError(404)
        if os.path.isfile(filepath):
            _, file_name = os.path.split(filepath)
            if file_name.startswith("."):
                raise HTTPError(404)

            self.set_header('Content-Type', 'application/force-download')
            self.set_header('Content-Disposition', f'attachment; filename=%s' % file_name)
            try:
                with open(filepath, "rb") as f:
                    while True:
                        _buffer = f.read(4096)
                        if _buffer:
                            self.write(_buffer)
                        else:
                            f.close()
                            self.finish()
                            return
            except:
                raise HTTPError(404)
        else:
            raise HTTPError(404)


class ExportAsHandler(JupyterHandler):
    SUPPORTED_METHODS = ("POST", )
    auth_resource = "nbconvert"

    @web.authenticated
    @authorized
    async def post(self, format):
        from jupyter_server.nbconvert.handlers import get_exporter, respond_zip
        from nbconvert.exporters.base import Exporter
        from nbformat import from_dict

        exporter: Exporter = get_exporter(format, config=self.config)
        model = self.get_json_body()
        assert model is not None
        name = model.get("name", "notebook.ipynb")
        nbnode = from_dict(model["content"])

        try:
            # attach additional options for export from json body to streamlined notebook exporter
            # options is a superclass field that does not exist on all exporters
            if format == "streamline":
                exporter.options = model["options"]
            output, resources = exporter.from_notebook_node(
                nbnode,
                resources={
                    "metadata": {"name": name[: name.rfind(".")]},
                    "config_dir": self.application.settings["config_dir"],
                }
            )
        except Exception as e:
            self.set_status(500)
            self.set_header("Content-Type", "application/json;charset=UTF-8")
            self.write(
                json.dumps({
                    "ename": e.__class__.__name__,
                    "evalue": str(e),
                    "traceback": traceback.format_exception(e),
                })
            )
            self.finish()
            return

        # Some exports generate multiple files. If so, they should be zipped. The respond_zip handles everything needed
        # to respond if it returns true, so no further action is needed in this function.
        if respond_zip(self, name, output, resources):
            return

        # Set download filename
        filename = os.path.splitext(name)[0] + resources["output_extension"]
        self.set_attachment_header(filename)

        # Set MIME type
        if exporter.output_mimetype:
            self.set_header("Content-Type", "%s; charset=utf-8" % exporter.output_mimetype)

        self.finish(output)


class SummaryHandler(ExtensionHandlerMixin, JupyterHandler):
    async def post(self):
        payload = json.loads(self.request.body)
        summary = await summarize(**payload)
        return self.write(summary)


class StatsHandler(ExtensionHandlerMixin, JupyterHandler):
    """
    """

    async def get(self):
        """
        """
        with open("/proc/sys/fs/file-nr") as filehandles:
            file_handle_details = filehandles.read().strip()
        fh_open, _, fh_total = map(int, file_handle_details.split())
        fh_usage = fh_open / fh_total * 100

        load_1, load_5, load_15 = [f"{avg:2f}" for avg in os.getloadavg()]
        mem_total, mem_used, mem_free = map(int, os.popen('free -t -m').readlines()[-1].split()[1:])
        disk_total, disk_used, disk_free, disk_usage, mount = list(os.popen('df -h .').readlines()[-1].split()[1:])


        # Fetch remote resources asynchronously
        (
            system_stats,
            sessions,
            kernels,
        ) = await asyncio.gather(
            admin_utils.fetch_system_stats(),
            self.session_manager.list_sessions(),
            admin_utils.fetch_kernel_info(self.kernel_manager),
        )
        ps_response, fh_response, lsof_response = system_stats

        proc_info = await admin_utils.build_proc_info(ps_response, fh_response)
        edges, kernel_by_pid_index = await admin_utils.build_edges_map(lsof_response, kernels)

        # Update each session with collected information
        for session in sessions:
            kernel_id = session.get("kernel", {}).get('id', None)
            kernel = kernels.get(kernel_id)
            session["kernel"].update(kernel)
            beaker_kernel_pid = kernels[kernel_id].get("pid", None)
            subkernel_pid = None
            if beaker_kernel_pid is not None:
                potential_subkernel_pids = [child for parent, child in edges if parent == beaker_kernel_pid]
                for psp in potential_subkernel_pids:
                    if psp in kernel_by_pid_index:
                        subkernel_pid = psp
                        session["subkernel"] = kernel_by_pid_index[psp]
                        break
            session["process_info"] = []
            pids_to_add = []
            if beaker_kernel_pid is not None:
                pids_to_add.append(beaker_kernel_pid)
            if subkernel_pid is not None:
                pids_to_add.append(subkernel_pid)
            while len(pids_to_add) > 0:
                pid = pids_to_add.pop()
                session["process_info"].append(proc_info[pid])
                for proc in proc_info.values():
                    if proc["ppid"] == pid:
                        pids_to_add.append(proc["pid"])

        output = {
            "file_handles": {
                "open": fh_open,
                "total": fh_total,
                "usage": f"{fh_usage:2f}"
            },
            "load": {
                "1_min": load_1,
                "5_min": load_5,
                "15_min": load_15,
            },
            "memory": {
                "total": mem_total,
                "used": mem_used,
                "free": mem_free,
                "usage": f"{int(mem_used/mem_total*100)}%",
            },
            "disk": {
                "total": disk_total,
                "used": disk_used,
                "free": disk_free,
                "usage": disk_usage,
                "mount": mount,
            },
            "sessions": sessions,
            "kernels": kernels,
            "token": config.jupyter_token,
        }
        return self.write(json.dumps(output))


def register_handlers(app: LabServerApp):
    pages = []

    beaker_app: BeakerApp = app.extension_config.get("app", None)
    if beaker_app and beaker_app.asset_dir:
        if os.path.isdir(beaker_app.asset_dir):
            app.handlers.append((f"/assets/{beaker_app.slug}/(.*)", StaticFileHandler, {"path": beaker_app.asset_dir}))

    routes = {}
    if beaker_app and beaker_app.pages:
        for page_name, page in beaker_app.pages.items():
            page_path = f"/{page_name}"
            routes[page_path] = {
                "path": page_path,
                "name": page_name,
            }
            if page.get("default", False):
                routes["/"] = {
                    "path": "/",
                    "name": "home",
                }

    else:
        route_file = Path(app.ui_path) / "routes.json"
        if route_file.exists():
            routes: dict[str, dict] = json.loads(route_file.read_text())
        else:
            # If no json file exists, ensure that at least 'home' exists
            routes = {
                "/": {
                    "path": "/",
                    "name": "home",
                },
            }

    if "/" not in routes:
        routes["/"] = {
            "path": "/",
            "name": "home",
        }

    for path, route in routes.items():
        name = route["name"]
        path = path.strip('/')
        if path.startswith(('_', '.')):
            continue
        if beaker_app and name != "home":
            if name in beaker_app.pages:
                pages.append(path)
        else:
            pages.append(path)
    page_regex = rf"/({'|'.join(pages)})"

    register_api_handlers(app)
    app.handlers.append(("/contexts", ContextHandler))
    app.handlers.append(("/config/control", ConfigController))
    app.handlers.append(("/config", ConfigHandler))
    app.handlers.append(("/stats", StatsHandler))
    app.handlers.append((r"/(favicon.ico|beaker.svg)$", StaticFileHandler, {"path": Path(app.ui_path)}))
    app.handlers.append((r"/summary", SummaryHandler))
    app.handlers.append((r"/export/(?P<format>\w+)", ExportAsHandler)),
    app.handlers.append((r"/((?:static|themes)/.*)", StaticFileHandler, {"path": Path(app.ui_path)})),
    app.handlers.append((page_regex, PageHandler, {"path": app.ui_path, "default_filename": "index.html"}))

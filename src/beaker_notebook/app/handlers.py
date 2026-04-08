import asyncio
import json
import logging
import os
import re
import traceback
import uuid
import urllib.parse
from importlib.metadata import entry_points, EntryPoints, EntryPoint
from typing import get_origin, get_args, Optional, TYPE_CHECKING
from dataclasses import is_dataclass
from pathlib import Path
from types import UnionType

from jupyter_server.auth.decorator import authorized, allow_unauthenticated
from jupyter_server.base.handlers import JupyterHandler
from jupyterlab_server import LabServerApp
from tornado import web, httputil
from tornado.web import StaticFileHandler, RequestHandler, HTTPError

from beaker_notebook.lib.autodiscovery import autodiscover, autodiscover_assets
from beaker_notebook.lib.app import BeakerApp
from beaker_notebook.lib.context import BeakerContext
from beaker_notebook.lib.subkernel import BeakerSubkernel
from beaker_notebook.lib.utils import normalize_notebook
from beaker_notebook.lib.config import config, locate_config, Config, Table, Choice, recursiveOptionalUpdate, reset_config
from beaker_notebook.lib import admin
from beaker_notebook.services.auth import BeakerUser
from beaker_notebook.services.context.manager import BeakerContextManager
from .api.handlers import register_api_handlers

if TYPE_CHECKING:
    from .base import BaseBeakerApp

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
    user: BeakerUser = handler.current_user
    logger.info(
        "%d %s %.2fms %s",
        handler.get_status(),
        handler._request_summary(),
        request_time,
        f": {user.username}" if user else "",
    )


class PageHandler(JupyterHandler, ):
    """
    Special handler that returns UI pages dynamically defined by the UI.
    """
    async def get(self, path: str, include_body: bool = True) -> None:

        # Always serve index.html as routing is performed in app.
        beakerapp: "BaseBeakerApp" = self.settings["serverapp"]
        base_url = beakerapp.base_url.rstrip('/')
        index_path = Path(beakerapp.ui_path).absolute() / "index.html"

        if not (index_path.exists() and index_path.is_file()):
            raise web.HTTPError(404, "File not found")

        session_id = None
        # If no session is provided on a root request, generate a session uuid and redirect to it
        if base_url and base_url.startswith('/session/'):
            session_id = base_url.replace('/session/', '')
        if not session_id:
            session_id = self.get_query_argument("session", None)
        if not session_id:
            session_id = str(uuid.uuid4())
            to_url = httputil.url_concat(
                f"{'/' if path.startswith('/') else '' }{path}",
                {"session": session_id},
            )
            return self.redirect(to_url, permanent=False)

        # Ensure a proper xsrf cookie value is set.
        cookie_name = self.settings.get("xsrf_cookie_name", "_xsrf")
        xsrf_token = self.xsrf_token.decode("utf8")
        xsrf_cookie = self.request.cookies.get(cookie_name, None)
        if not xsrf_cookie or xsrf_cookie.value != xsrf_token:
            kwargs = self.settings.get("xsrf_cookie_kwargs", {})
            self.set_cookie(cookie_name, xsrf_token, **kwargs)


        # Read the index.html
        html = index_path.read_text()

        # Build configuration object
        config = {
            'pathPrefix': base_url,
            'username': self.current_user.name if self.current_user else None,
            '_xsrf': self.xsrf_token.decode(),
        }
        env_vars = self.get_env()
        if env_vars:
            config["env"] = env_vars

        # Replace the Jinja2 placeholder with actual JSON
        # The index.html has: <script id="site-config" type="application/json">{{ siteConfig }}</script>
        config_json = json.dumps(config)
        # html = html.replace('{{ siteConfig }}', config_json)
        html = html.replace("</head>", f'<script id="site-config" type="application/json">{config_json}</script>\n</head>')
        html = html.replace(r'href="/', rf'href="{base_url}/')
        html = html.replace(r'src="/', rf'src="{base_url}/')

        self.set_header('Content-Type', 'text/html')
        self.write(html)

    def get_env(self) -> dict[str, str]:
        envs = {key: value for key, value in os.environ.items() if key.startswith("BEAKER_UI_")}
        return envs



class ConfigController(JupyterHandler):
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

class ConfigHandler(JupyterHandler):
    """
    Provide config via an endpoint
    """

    @allow_unauthenticated
    def get(self):
        # If BASE_URL is not provided in the environment, assume that the base url is the same location that
        # is handling this request, as reported by the request headers.
        # If APP_URL is not provided, assume it is the same as BASE_URL.

        beakerapp: "BaseBeakerApp" = self.settings["serverapp"]
        base_path = beakerapp.base_url or "/"

        base_url = os.environ.get("JUPYTER_BASE_URL", f"{self.request.protocol}://{self.request.host}{base_path}")

        base_scheme = urllib.parse.urlparse(base_url).scheme
        if base_scheme.endswith("s"):
            ws_scheme = "wss"
        else:
            ws_scheme = "ws"
        ws_url = base_url.replace(base_scheme, ws_scheme)

        beaker_app: BeakerApp|None = self.config.get("app", None)
        token = config.jupyter_token or self.identity_provider.token

        config_data = {
            "appUrl": os.environ.get("APP_URL", base_url),
            "baseUrl": base_url,
            "wsUrl": os.environ.get("JUPYTER_WS_URL", ws_url),
            "token": token,
            "config_type": config.config_type,
            "defaultKernel": self.kernel_spec_manager.get_default_kernel_name(),
            "extra": {}
        }
        if hasattr(config, "send_notebook_state"):
            config_data["extra"]["send_notebook_state"] = config.send_notebook_state
        if beaker_app:
            config_data["appConfig"] = beaker_app.as_dict()

        # Include resolved routes (with any dynamic import definitions from asset routes.json)
        resolved_routes = getattr(beakerapp, "resolved_routes", None)
        if resolved_routes:
            config_data["routes"] = resolved_routes

        # Ensure a proper xsrf cookie value is set.
        cookie_name = self.settings.get("xsrf_cookie_name", "_xsrf")
        xsrf_token = self.xsrf_token.decode("utf8")
        xsrf_cookie = self.request.cookies.get(cookie_name, None)
        if not xsrf_cookie or xsrf_cookie.value != xsrf_token:
            kwargs = self.settings.get("xsrf_cookie_kwargs", {})
            self.set_cookie(cookie_name, xsrf_token, **kwargs)

        return self.write(config_data)


class ContextHandler(JupyterHandler):
    """
    Provide information about llm contexts via an endpoint
    """
    provisioners: EntryPoints

    def __init__(self, application, request, **kwargs):
        super().__init__(application, request, **kwargs)
        self.provisioners = entry_points(group="jupyter_client.kernel_provisioners")

    def get(self):
        """Get the main page for the application's interface."""
        ksm = self.kernel_spec_manager
        context_manager: BeakerContextManager = self.serverapp.context_manager
        contexts = sorted(context_manager.list_contexts(), key=lambda context: context.weight)
        possible_subkernels: dict[str, BeakerSubkernel] = autodiscover("subkernels")
        subkernel_by_kernel_index = {subkernel.KERNEL_NAME: subkernel for subkernel in possible_subkernels.values()}
        subkernel_by_language_index = {subkernel.JUPYTER_LANGUAGE: subkernel for subkernel in possible_subkernels.values()}
        kernels = ksm.get_all_specs()

        # TODO: This context/subkernel logic needs to be redone
        installed_kernels = {}
        for kernel_long_name, kernel_details in kernels.items():
            kernelspec = kernel_details.get("spec", {})
            kernel_name = kernelspec.get("name", kernel_long_name)
            kernel_language = kernelspec.get("language", kernel_name)

            if kernel_language in subkernel_by_language_index:
                installed_kernels[kernel_long_name] = {
                    "kernelspec": kernel_details,
                    "subkernel": subkernel_by_language_index[kernel_language],
                }

        # Extract data from auto-discovered contexts and subkernels to provide options
        context_data = {
            context.slug: {
                "languages": [
                    {
                        "slug": subkernel["language"],
                        "subkernel": subkernel["slug"],
                        "display": subkernel["display_name"],
                    }
                    for subkernel in context.subkernels.values()
                    if subkernel["slug"] in {installed_kernel["subkernel"].SLUG for installed_kernel in installed_kernels.values()}
                ],
                "subkernels": {
                    subkernel_slug: {
                        "language": subkernel["language"],
                        "slug": subkernel_slug,
                        "display_name": subkernel["display_name"],
                        "weight": subkernel["weight"],
                    }
                    for subkernel_slug, subkernel in context.subkernels.items()
                },
                "defaultPayload": context.cls.default_payload() if context.cls else '{}',  # TODO: Figure out if there's
                                                                                           # a clean way to track this
            }
            for context in contexts
        }
        return self.write(context_data)


class ExportAsHandler(JupyterHandler):
    SUPPORTED_METHODS = ("POST", )
    auth_resource = "nbconvert"

    @web.authenticated
    @authorized
    async def post(self, format):
        from jupyter_server.nbconvert.handlers import get_exporter, respond_zip
        from nbconvert.exporters.base import Exporter

        exporter: Exporter = get_exporter(format, config=self.config)
        model = self.get_json_body()
        assert model is not None
        name = model.get("name", "notebook.ipynb")
        nbnode = normalize_notebook(model["content"])

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


class StatsHandler(JupyterHandler):
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
            admin.fetch_system_stats(),
            self.session_manager.list_sessions(),
            admin.fetch_kernel_info(self.kernel_manager),
        )
        ps_response, fh_response, lsof_response = system_stats

        proc_info = await admin.build_proc_info(ps_response, fh_response)
        edges, kernel_by_pid_index = await admin.build_edges_map(lsof_response, kernels)

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


def register_handlers(app: "BaseBeakerApp"):
    pages = []
    app_pages = []  # list(beaker_app.pages or []) + [route["name"] for route in app_routes_data.values() if "name" in route]
    routes = {}

    # Serve package-level asset directories discovered via beaker.assets entry points
    package_assets = autodiscover_assets()
    for pkg_name, asset_dir in package_assets.items():
        app.handlers.append((f"/assets/package/{pkg_name}/(.*)", StaticFileHandler, {"path": asset_dir}))

    beaker_app: Optional[BeakerApp] = app.config.get("app", None)

    # Build routes with merge semantics: defaults → app pages → asset routes.json
    # Each layer overrides matching paths from previous layers.

    # 1. Start with default routes
    route_file = Path(app.ui_path) / "routes.json"
    if route_file.exists():
        routes = json.loads(route_file.read_text())
    else:
        routes = {
            "/": {
                "path": "/",
                "name": "home",
            },
        }

    # 2. App pages override/extend defaults
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

    # 3. Asset routes.json overrides/extends everything (supports dynamic page imports)
    if beaker_app and beaker_app.asset_dir:
        if os.path.isdir(beaker_app.asset_dir):
            app.handlers.append((f"/assets/{beaker_app.slug}/(.*)", StaticFileHandler, {"path": beaker_app.asset_dir}))
            app_routes_path = os.path.join(beaker_app.asset_dir, "routes.json")
            if os.path.isfile(app_routes_path):
                with open(app_routes_path) as app_routes_file:
                    app_routes_data = json.load(app_routes_file)
                    if isinstance(app_routes_data, dict):
                        # Resolve relative import paths to absolute asset URLs
                        # and normalize keys to use the path field
                        asset_base_url = f"/assets/{beaker_app.slug}"
                        for route_key, route_data in list(app_routes_data.items()):
                            if "import" in route_data and not route_data["import"].startswith("/"):
                                route_data["import"] = f"{asset_base_url}/{route_data['import']}"
                            # Ensure route has a path (use key if not explicitly set)
                            if "path" not in route_data:
                                route_data["path"] = route_key if route_key.startswith("/") else f"/{route_key}"
                            # Ensure route has a name (use key if not explicitly set)
                            if "name" not in route_data:
                                route_data["name"] = route_key.strip("/") or "home"
                        # Re-key by path so it merges correctly with the other route sources
                        for route_key, route_data in list(app_routes_data.items()):
                            path_key = route_data["path"]
                            if path_key != route_key:
                                app_routes_data[path_key] = route_data
                                del app_routes_data[route_key]
                        routes.update(app_routes_data)

    if "/" not in routes:
        routes["/"] = {
            "path": "/",
            "name": "home",
        }

    # Store resolved routes on the app so ConfigHandler can include them
    app.resolved_routes = routes

    for path, route in routes.items():
        name = route["name"]
        path = path.strip('/')
        if path.startswith(('_', '.')):
            continue
        if beaker_app and beaker_app.pages and name != "home":
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
    app.handlers.append((r"/export/(?P<format>\w+)", ExportAsHandler)),
    app.handlers.append((r"/((?:static|themes)/.*)", StaticFileHandler, {"path": Path(app.ui_path)})),
    app.handlers.append((page_regex, PageHandler))

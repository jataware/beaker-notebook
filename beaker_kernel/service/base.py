import getpass
import inspect
import logging
import os
import pwd
import re
import shutil
import signal
import urllib.parse
from typing import Optional, Any, cast, ClassVar

import traitlets
from traitlets import Unicode, Integer, Float
from traitlets.config.application import Application, ClassesType
from traitlets.config.configurable import Configurable
from traitlets.config.loader import ConfigFileNotFound
from traitlets.utils.text import indent, wrap_paragraphs

from jupyter_client.ioloop.manager import AsyncIOLoopKernelManager
from jupyter_client import kernelspec
from jupyter_server.services.kernels.kernelmanager import AsyncMappingKernelManager
from jupyter_server.services.sessions.sessionmanager import SessionManager
from jupyter_server.serverapp import ServerApp

from beaker_kernel.lib.app import BeakerApp
from beaker_kernel.lib.autodiscovery import autodiscover
from beaker_kernel.lib.config import config, CONFIG_FILE_SEARCH_LOCATIONS
from beaker_kernel.lib.utils import import_dotted_class
from beaker_kernel.service.auth import current_user, BeakerUser, BeakerAuthorizer, BeakerIdentityProvider
from beaker_kernel.service.handlers import register_handlers, request_log_handler


logger = logging.getLogger("beaker_server")
HERE = os.path.dirname(__file__)

version = "1.0.0"


class BeakerSessionManager(SessionManager):

    async def prune_sessions(self, all=False) -> int:
        """
        Removes sessions from the session store.

        Parameters
        ----------
        all : bool
            If true, all sessions are removed.
            If false, only sessions without active kernels are removed.

        Returns
        -------
        int
            Number of sessions pruned.
        """
        count = 0
        all_sessions = await self.list_sessions(include_missing=True)
        for session in all_sessions:
            kernel_model = session.get("kernel", None)
            kernel_id = kernel_model and kernel_model.get("id")
            if all or await self.kernel_culled(kernel_id):
                await self.delete_session(session_id=session["id"])
                count += 1
        return count

    async def list_sessions(self, include_missing=False) -> list[dict]:
        return await super().list_sessions()


    def get_kernel_env(self, path, name = None):
        """Get environment variables for Beaker kernel sessions.

        Sets up environment variables including session name, Beaker session,
        and user information for kernel execution.

        Parameters
        ----------
        path : str
            Session path
        name : str, optional
            Session name

        Returns
        -------
        dict
            Environment variables for kernel
        """
        # This only sets env variables for the Beaker Kernel, not subkernels.
        try:
            beaker_user = path.split(os.path.sep)[0]
        except:
            pass
        env = {
            **os.environ,
            "JPY_SESSION_NAME": path,
            "BEAKER_SESSION": str(name),
        }
        if beaker_user:
            env.update({
                "BEAKER_USER": beaker_user,
                "LANGSMITH_BEAKER_USER": beaker_user,
            })

        return env

    async def start_kernel_for_session(self, session_id, path, name, type, kernel_name):
        """Start a kernel for a session with user-specific path and permissions.

        For Beaker kernels, sets up user-specific home directories and proper
        file permissions for the subkernel user.

        Parameters
        ----------
        session_id : str
            Unique identifier for the session
        path : str
            Path for the session
        name : str
            Session name
        type : str
            Session type
        kernel_name : str
            Name of the kernel to start

        Returns
        -------
        dict
            Session information from parent class
        """
        user: BeakerUser = current_user.get()
        if user:
            virtual_home_root = self.parent.virtual_home_root
            virtual_home_dir = os.path.join(virtual_home_root, user.home_dir)

            subkernel_user = self.parent.subkernel_user
            if not os.path.isdir(virtual_home_dir):
                os.makedirs(virtual_home_dir, exist_ok=True)
                shutil.chown(virtual_home_dir, user=subkernel_user, group=subkernel_user)
            path = os.path.relpath(virtual_home_dir, self.kernel_manager.root_dir)

        kernel_env = self.get_kernel_env(path, name)
        kernel_id = await self.kernel_manager.start_kernel(
            path=path,
            kernel_name=kernel_name,
            env=kernel_env,
        )
        return cast(str, kernel_id)


class BeakerKernelSpecManager(kernelspec.KernelSpecManager):
    NAME_SEP = r"%%"
    parent: "traitlets.Instance[BaseBeakerApp]"

    @property
    def kernel_spec_managers(self) -> dict[str, kernelspec.KernelSpecManager]:
        """Get kernel specification managers from parent server app.

        Returns
        -------
        dict[str, kernelspec.KernelSpecManager]
            Mapping of extension names to kernel spec managers
        """
        return self.parent.kernel_spec_managers

    def get_default_kernel_name(self) -> str:
        """Get the default kernel name.

        Returns
        -------
        str
            The default kernel name (beaker_kernel)
        """
        return f"beaker_kernel"

    def _update_spec(self, name: str, spec: dict[str, dict]) -> dict[str, dict]:
        """Update kernel spec with name if not present.

        Parameters
        ----------
        name : str
            Kernel name to add to spec
        spec : dict[str, dict]
            Kernel specification dictionary

        Returns
        -------
        dict[str, dict]
            Updated kernel specification
        """
        if "name" not in spec:
            spec["name"] = name
        return spec

    def get_all_specs(self) -> dict[str, dict]:
        """Get all available kernel specifications from all managers.

        Aggregates kernel specifications from local manager and all extension
        managers, applying proper namespacing for extension specs.

        Returns
        -------
        dict[str, dict]
            Dictionary mapping kernel names to their specifications
        """
        res = {}
        for spec_slug, spec_manager in self.kernel_spec_managers.items():

            if not self.parent.kernel_spec_include_local and spec_slug is None:
                # Even we are not including local specs, we need to include beaker_kernel
                res["beaker_kernel"] = self._update_spec(spec_manager.get_all_specs()["beaker_kernel"])

            specs = spec_manager.get_all_specs().items()
            for kernel_name, spec in specs:
                if spec_slug is None:
                    key = kernel_name
                else:
                    key = f"{spec_slug}{self.NAME_SEP}{kernel_name}"
                res[key] = self._update_spec(kernel_name, spec)
        return res

    def get_kernel_spec(self, kernel_name) -> kernelspec.KernelSpec:
        """Get a specific kernel specification by name.

        Handles both local kernel specs and extension-namespaced specs.
        Extension specs use the format: extension_name%%kernel_name

        Parameters
        ----------
        kernel_name : str
            Name of the kernel spec to retrieve, optionally namespaced

        Returns
        -------
        kernelspec.KernelSpec
            The requested kernel specification

        Raises
        ------
        kernelspec.NoSuchKernel
            If the specified kernel is not found
        """
        if self.NAME_SEP in kernel_name:
            spec_slug, name = kernel_name.split(self.NAME_SEP, maxsplit=1)
        else:
            spec_slug = None
            name = kernel_name

        spec_manager = self.kernel_spec_managers.get(spec_slug, None)
        if spec_manager is None:
            raise kernelspec.NoSuchKernel(kernel_name)

        spec = spec_manager.get_kernel_spec(name)

        if spec is None:
            raise kernelspec.NoSuchKernel(kernel_name)

        # spec = super().get_kernel_spec(kernel_name)
        # if kernel_name == "beaker_kernel":
        #     return spec
        # elif self.parent.provisioner_class:
        #     provisioner_obj = {
        #         "provisioner_name": "beaker-docker-provisioner",
        #         "config": {
        #             "image": "beaker-kernel-python",
        #             "max_cpus": 4,
        #         },
        #     }
        #     spec.metadata["kernel_provisioner"] = provisioner_obj
        return spec



class BeakerKernelManager(AsyncIOLoopKernelManager):
    beaker_session = Unicode(allow_none=True, help="Beaker session identifier", config=True)

    # Longer wait_time for shutdown before killing processed due to potentially needing to shutdown both the subkernel
    # and the beaker kernel.
    shutdown_wait_time = Float(
        10.0,
        help="Time to wait for shutdown before killing processes",
        config=True
    )


    @property
    def beaker_config(self):
        """Get Beaker configuration from parent.

        Returns
        -------
        dict
            Beaker configuration dictionary
        """
        return getattr(self.parent, 'beaker_config')

    @property
    def app(self) -> "BaseBeakerApp":
        """Get the BeakerServerApp instance.

        Returns
        -------
        BeakerServerApp
            The server application instance
        """
        return self.parent.parent

    def write_connection_file(self, **kwargs: object) -> None:
        """Write kernel connection file with Beaker-specific context.

        Extends the standard connection file with Beaker session information,
        server URL, and default context from the Beaker application.

        Parameters
        ----------
        **kwargs : object
            Additional connection file parameters
        """
        beaker_session: Optional[str] = self.beaker_session
        jupyter_session: Optional[str] = kwargs.get("jupyter_session", None)
        if beaker_session:
            kwargs["beaker_session"] = beaker_session
        if jupyter_session:
            kwargs["jupyter_session"] = jupyter_session
        beaker_app: BeakerApp = self.beaker_config.get("app", None)
        default_context = beaker_app and beaker_app._default_context
        if default_context:
            app_context_dict = default_context.asdict()
            kwargs['context'] = {
                "default_context": default_context.slug,
                "default_context_payload": default_context.payload,
            }
            if app_context_dict:
                kwargs["context"].update(**app_context_dict)

        super().write_connection_file(
            server=self.app.public_url,
            **kwargs
        )

        # Set file to be owned by and modifiable by the beaker user so the beaker user can modify the file.
        os.chmod(self.connection_file, 0o0775)
        shutil.chown(self.connection_file, user=self.app.agent_user)

    async def _async_pre_start_kernel(self, **kw):
        """Pre-start kernel setup including user switching and environment setup.

        Configures the kernel environment with appropriate user permissions,
        working directory, and environment variables before kernel launch.

        Parameters
        ----------
        **kw
            Keyword arguments for kernel startup

        Returns
        -------
        tuple
            Command and keyword arguments for kernel launch
        """
        # Stash beaker_session value so it can be written in the connection file.
        beaker_session = kw.get('env', {}).get('BEAKER_SESSION', None) or kw.get("session_path", None)
        if beaker_session and not self.beaker_session:
            self.beaker_session = beaker_session

        cmd, kw = await super()._async_pre_start_kernel(**kw)

        env = kw.pop("env", {})

        # Update user, env variables, and home directory based on type of kernel being started.
        if self.kernel_name == "beaker_kernel":
            kernel_user = self.app.agent_user
            home_dir = os.path.expanduser(f"~{kernel_user}")
            kw["cwd"] = home_dir
            env["HOME"] = home_dir
        else:
            kernel_user = self.app.subkernel_user
            home_dir = kw.get("cwd")

        user_info = pwd.getpwnam(kernel_user)
        home_dir = os.path.expanduser(f"~{kernel_user}")
        group_list = os.getgrouplist(kernel_user, user_info.pw_gid)
        if user_info.pw_uid != os.getuid():
            env["USER"] = kernel_user
            kw["user"] = kernel_user
            env["HOME"] = home_dir
        if os.getuid() == 0 or os.geteuid() == 0:
            kw["group"] = user_info.pw_gid
            kw["extra_groups"] = group_list[1:]

        # Update keyword args that are passed to Popen()
        kw["env"] = env

        return cmd, kw
    pre_start_kernel = _async_pre_start_kernel

    async def _async_launch_kernel(self, kernel_cmd, **kw):
        kw.pop("session_path", None)
        return await super()._async_launch_kernel(kernel_cmd, **kw)

    async def _async_interrupt_kernel(self):
        if self.shutting_down and self.kernel_name == "beaker_kernel":
            # During shutdown, interrupt Beaker kernel instances without interrupting the subkernel which is being
            # interrupted/shutdown in parallel by the server.
            # Sending an INTERRUPT signal notifies beaker to interrupt without affecting the subkernel.
            # Normal interrupts are done via a interrupt message, which will also interrupt the subkernel.
            return await self._async_signal_kernel(signal.SIGINT)
        return await super()._async_interrupt_kernel()


class BeakerKernelMappingManager(AsyncMappingKernelManager):
    kernel_manager_class = traitlets.DottedObjectName("beaker_kernel.service.base.BeakerKernelManager")
    connection_dir = Unicode(
        os.path.join(config.beaker_run_path, "kernelfiles"),
        help="Directory for kernel connection files",
        config=True
    )
    cull_idle_timeout = Integer(
        0,
        help="Timeout in seconds for culling idle kernels",
        config=True
    )

    def __init__(self, **kwargs):
        """Initialize BeakerKernelMappingManager.

        Sets up the connection directory and initializes the kernel manager
        with default kernel name if available.

        Parameters
        ----------
        **kwargs
            Additional arguments passed to parent class
        """
        # Ensure connection dir exists and is readable
        if not os.path.isdir(self.connection_dir):
            os.makedirs(self.connection_dir, mode=0o0755)
        else:
            os.chmod(self.connection_dir, 0o0755)
        super().__init__(**kwargs)
        if hasattr(self.kernel_spec_manager, "get_default_kernel_name"):
            self.default_kernel_name = self.kernel_spec_manager.get_default_kernel_name()

    @property
    def beaker_config(self):
        return getattr(self.parent, 'beaker_config', None)

    def cwd_for_path(self, path, **kwargs):
        user: BeakerUser = current_user.get()
        if user:
            user_home = self.get_home_for_user(user)
            return super().cwd_for_path(user_home, **kwargs)
        else:
            return super().cwd_for_path(path, **kwargs)

    def get_home_for_user(self, user: BeakerUser) -> os.PathLike:
        return user.home_dir

    async def _async_start_kernel(self, *, kernel_id = None, path = None, **kwargs):
        kwargs.setdefault('session_path', path)
        return await super()._async_start_kernel(kernel_id=kernel_id, path=path, **kwargs)
    start_kernel = _async_start_kernel

    def pre_start_kernel(self, kernel_name: str, kwargs: dict):
        km, kernel_name, kernel_id = super().pre_start_kernel(kernel_name, kwargs)
        km = cast(BeakerKernelManager, km)
        beaker_session = kwargs.get("session_path", None)
        if beaker_session and not km.beaker_session:
            km.beaker_session = beaker_session
        return km, kernel_name, kernel_id

    async def cull_kernel_if_idle(self, kernel_id):
        """Cull a kernel if it is idle."""
        kernel = self._kernels.get(kernel_id, None)
        if getattr(kernel, "kernel_name", None) != "beaker_kernel":
            return
        result = await super().cull_kernel_if_idle(kernel_id)
        return result

class BaseBeakerApp(ServerApp):
    """
    Customizable ServerApp for use with Beaker
    """
    defaults: ClassVar[dict] = {}

    name = traitlets.Unicode("beaker", config=True)
    app_slug = traitlets.Unicode(config=True)

    kernel_manager_class = traitlets.Type(
        f"{__package__}.base.BeakerKernelMappingManager",
        config=True
    )
    session_manager_class = traitlets.Type(
        f"{__package__}.base.BeakerSessionManager",
        config=True
    )
    contents_manager_class = traitlets.Type(
        klass=f"{__package__}.storage.base.BaseBeakerContentsManager",
        default_value=f"{__package__}.storage.base.BeakerLocalContentsManager",
        config=True,
    )
    kernel_spec_manager_class = traitlets.Type(
        f"{__package__}.base.BeakerKernelSpecManager",
        config=True
    )
    notebook_manager_class = traitlets.Type(
        f"{__package__}.storage.notebook.BaseNotebookManager",
        # default_value=f"{__package__}.storage.notebook.FileNotebookManager",
        config=True
    )
    virtual_home_root = traitlets.Unicode(
        help="Path pointing to where user directories should be stored. Defaults to 'root_dir' if not set.",
        config=True,
    )

    kernel_spec_include_local = traitlets.Bool(True, help="Include local kernel specs", config=True)
    kernel_spec_managers = traitlets.Dict(help="Kernel specification managers indexed by extension name", config=True)

    beaker_extensions = traitlets.Dict(help="Auto-discovered Beaker extensions providing additional contexts and subkernels")
    beaker_extension_app = traitlets.Dict(help="", config=True)

    service_user = Unicode(help="Username under which the Beaker service is running", config=True)
    agent_user = Unicode(help="Username for the Beaker kernel agent process", config=True)
    subkernel_user = Unicode(help="Username under which subkernels (Python, R, etc.) are executed", config=True)
    working_dir = Unicode(help="Working directory for kernel execution and file operations", config=True)
    ui_path = Unicode(help="Working directory for kernel execution and file operations", config=True)
    log_requests = traitlets.Bool(False, help="Enable request logging", config=True)

    allow_origin = traitlets.Unicode("*", config=True)
    disable_check_xsrf = traitlets.Bool(True)
    open_browser = traitlets.Bool(False, config=True)
    extension_url = traitlets.Unicode("/", config=True)
    connection_dir = traitlets.Unicode("", config=True)

    config_file_name = traitlets.Unicode(config=True)
    beaker_config_path = traitlets.Union(trait_types=[traitlets.List(trait=traitlets.Unicode()), traitlets.Unicode()], config=True)

    @classmethod
    def _app_slug(cls):
        cls_name = cls.__name__
        parts_to_remove = {"", "Beaker", "Base", "App"}
        parts = re.split(r'([A-Z][a-z]*)', cls_name)
        parts = [part.lower() for part in parts if part and part not in parts_to_remove]
        return "_".join(parts)

    @traitlets.default("ui_path")
    def _default_ui_path(self):
        return os.path.join(os.path.dirname(__file__), "ui")

    @traitlets.default("identity_provider_class")
    def _default_identity_provider_class(self):
        from beaker_kernel.service.auth.notebook import NotebookIdentityProvider
        return NotebookIdentityProvider

    @traitlets.default("authorizer_class")
    def _default_authorizer_class(self):
        from beaker_kernel.service.auth.notebook import NotebookAuthorizer
        return NotebookAuthorizer

    @traitlets.default("config_file_name")
    def _default_config_file_name(self):
        if self.app_slug:
            return f"beaker_{self.app_slug}_config"
        else:
            return f"beaker_config"

    @traitlets.default("beaker_config_path")
    def _default_beaker_config_path(self):
        return [str(path) for (path, *_) in CONFIG_FILE_SEARCH_LOCATIONS]

    @traitlets.default("app_slug")
    def _default_app_slug(self):
        return self._app_slug()

    @traitlets.default("notebook_manager_class")
    def _default_notebook_manager_class(self):
        from beaker_kernel.service.storage.notebook import FileNotebookManager
        return FileNotebookManager

    def __init__(self, **kwargs):
        # Apply defaults from defaults classvar
        defaults = getattr(self.__class__, "defaults", None)
        if defaults and isinstance(defaults, dict):
            from traitlets.config import Config

            if config.jupyter_token:
                identity_dict = defaults.get("IdentityProvider", {})
                identity_dict.setdefault("token", config.jupyter_token)
                defaults["IdentityProvider"] = identity_dict

            trait_config = Config(**defaults)
            self.config.update(trait_config)

            kwargs.update(defaults)
        super().__init__(**kwargs)

    def init_configurables(self):
        # Initialize configurables first to ensure config is loaded before other initializations
        super().init_configurables()

        self.notebook_manager = self.notebook_manager_class(
            parent=self,
            # contents_manager=self.contents_manager
        )

    def initialize(self, argv = None, find_extensions = False, new_httpserver = True, starter_extension = None):
        super().initialize(argv, find_extensions, new_httpserver, starter_extension)
        beaker_app_slug = os.environ.get("BEAKER_APP", self.config.get("beaker_app", None))
        if beaker_app_slug:
            app_cls: type[BeakerApp] = import_dotted_class(beaker_app_slug)
            beaker_app: BeakerApp = app_cls()

            self.config.update({
                "app_cls": app_cls,
                "app": beaker_app,
            })
        else:
            self.config.update({
                "app_cls": None,
                "app": None,
            })
        self.initialize_handlers()

    def initialize_handlers(self):
        """Bypass initializing the default handler since we don't need to use the webserver, just the websockets."""
        self.handlers = []
        register_handlers(self)
        self.web_app.add_handlers(".*", self.handlers)

    def load_config_file(self, suppress_errors = True):
        default_config_files = (self._default_config_file_name(), "beaker_config")
        try:
            # Load default configuration files first
            for default_config_file_name in default_config_files:
                try:
                    Application.load_config_file(self, default_config_file_name, path=self.beaker_config_path)
                except ConfigFileNotFound:
                    self.log.debug("Config file not found, skipping: %s", self.config_file_name)

            # If another configuration file is defined, load it second so it overrides any defaults
            if self.config_file_name != default_config_file_name:
                try:
                    Application.load_config_file(self, self.config_file_name, path=self.beaker_config_path)
                except ConfigFileNotFound:
                    self.log.debug("Config file not found, skipping: %s", self.config_file_name)
        except Exception:
            # Reraise errors for testing purposes, or if set in self.raise_config_file_errors
            if (not suppress_errors) or self.raise_config_file_errors:
                raise
            self.log.warning("Error loading config file: %s", self.config_file_name, exc_info=True)

    @traitlets.default('beaker_extensions')
    def _default_beaker_extensions(self):
        return {k: v for k, v in autodiscover("extensions").items()}

    @traitlets.default('service_user')
    def _default_service_user(self):
        return getpass.getuser()

    @traitlets.default('agent_user')
    def _default_agent_user(self):
        if self.service_user == "root":
            agent_user = os.environ.get("BEAKER_AGENT_USER", None)
            if agent_user is None:
                raise RuntimeError("When running as root, BEAKER_AGENT_USER environment variable must be set.")
            return agent_user
        else:
            return os.environ.get("BEAKER_AGENT_USER", self.service_user)

    @traitlets.default('subkernel_user')
    def _default_subkernel_user(self):
        if self.service_user == "root":
            subkernel_user = os.environ.get("BEAKER_SUBKERNEL_USER", None)
            if subkernel_user is None:
                raise RuntimeError("When running as root, BEAKER_SUBKERNEL_USER environment variable must be set.")
            return subkernel_user
        else:
            return os.environ.get("BEAKER_SUBKERNEL_USER", self.service_user)

    @traitlets.default('working_dir')
    def _default_working_dir(self):
        if self.service_user == "root":
            return os.path.expanduser(f"~{self.subkernel_user}")
        else:
            return os.getcwd()

    @traitlets.default('kernel_spec_managers')
    def _default_kernel_spec_managers(self):
        result = {}
        # Add local kernel specs in enabled first
        if self.kernel_spec_include_local:
            local_kernel_spec_manager = kernelspec.KernelSpecManager(parent=self)
            result[None] = local_kernel_spec_manager

        # Add kernel specs from extensions
        for extension_slug, extension_cls in self.beaker_extensions.items():
            spec_manager = getattr(extension_cls, "kernel_spec_manager_class", None)
            if spec_manager:
                result[extension_slug] = spec_manager(parent=self)
        return result

    @traitlets.default("virtual_home_root")
    def _default_virtual_home_root(self):
        return self.root_dir

    @property
    def _default_root_dir(self):
        return self.working_dir or super()._default_root_dir()

    def stop(self, from_signal = False):
        print("Shutting down Beaker server...")
        return super().stop(from_signal)

    @property
    def beaker_config(self):
        return self.config

    @property
    def public_url(self):
        return f"http://{self.ip}:{self.port}/"

    @property
    def local_url(self):
        return self.public_url

    @property
    def display_url(self):
        return f"    {self.public_url}"

    def _get_urlparts(self, path: str | None = None, include_token: bool = False) -> urllib.parse.ParseResult:
        # Always return urls without tokens
        return super()._get_urlparts(path, False)

    def generate_config_file(self, classes: ClassesType | None = None) -> str:
        """Generate default config file from Configurables"""
        lines = [
            "# ===========================================",
            "# Beaker Notebook Service Configuration File",
            "# ===========================================",
            "# This file demonstrates all configurable traitlets in the Beaker Notebook service.",
            "# Copy this file to jupyter_server_config.py or beaker_config.py in your Jupyter config directory.",
            "# Uncomment and modify values as needed for your deployment.",
            "",
            "c = get_config()  # noqa",
            "",
        ]

        def class_sort_key(cls: type):
            if cls == self.__class__:
                return -1, cls.__module__, cls.__name__
            if 'jupyter' in cls.__module__ or 'nbformat' in cls.__module__ or 'traitlets' in cls.__module__:
                return 1, cls.__module__, cls.__name__
            return 0, cls.__module__, cls.__name__
            # return cls.__name__

        classes = self.classes if classes is None else classes

        extended_classes = []
        extended_classes.extend([subclass for _, subclass in inspect.getmembers(self, inspect.isclass) if subclass not in classes])
        extended_classes.extend([subclass.__class__ for _, subclass in inspect.getmembers(self, lambda obj: isinstance(obj, Configurable)) if subclass.__class__ not in classes])
        extended_classes.extend([extension for extension in getattr(self, 'beaker_extensions', {}).values() if extension not in classes])
        classes.extend(extended_classes)

        config_classes = list(self._classes_with_config_traits(classes))
        config_classes.sort(key=class_sort_key)
        added = set()
        for cls in config_classes:
            lines.append(self.generate_config_section(cls, config_classes, added))
        return "\n".join(lines)

    def generate_config_section(self, cls, classes, added):
        def c(s: str) -> str:
            """return a commented, wrapped block."""
            s = "\n\n".join(wrap_paragraphs(s, 78))

            return "## " + s.replace("\n", "\n#  ")
        adding = set()

        # section header
        breaker = "#" + "-" * 78
        parent_classes = ", ".join(p.__name__ for p in cls.__bases__ if issubclass(p, Configurable))

        s = f"# {cls.__name__}({parent_classes}) configuration"
        lines = [breaker, s, breaker]
        # get the description trait
        desc = cls.class_traits().get("description")
        if desc:
            desc = desc.default_value
        if not desc:
            # no description from trait, use __doc__
            desc = getattr(cls, "__doc__", "")  # type:ignore[arg-type]
        if desc:
            lines.append(c(desc))  # type:ignore[arg-type]
            lines.append("")

        for name, trait in sorted(cls.class_traits(config=True).items()):
            default_repr = trait.default_value_repr()
            if trait in added:
                continue


            if trait.help:
                if 'deprecated' in trait.help.lower():
                    continue
                lines.append(c(trait.help))
            if "Enum" in type(trait).__name__:
                # include Enum choices
                lines.append("#  Choices: %s" % trait.info())
            lines.append("#  Default: %s" % default_repr)

            lines.append(f"# c.{cls.__name__}.{name} = {default_repr}")
            lines.append("")
            adding.add(trait)

        if adding:
            added.update(adding)
            return "\n".join(lines)
        else:
            return ""

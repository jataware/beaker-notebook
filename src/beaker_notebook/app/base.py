import getpass
import inspect
import logging
import os
import re
import urllib.parse
from typing import ClassVar

import traitlets
from traitlets.traitlets import Unicode
from traitlets.config import Config
from traitlets.config.application import Application, ClassesType
from traitlets.config.configurable import Configurable
from traitlets.config.loader import ConfigFileNotFound
from traitlets.utils.text import wrap_paragraphs

from jupyter_client import kernelspec
from jupyter_server.serverapp import ServerApp
from jupyter_server.utils import url_path_join

from beaker_notebook.lib.app import BeakerApp
from beaker_notebook.lib.autodiscovery import autodiscover
from beaker_notebook.lib.config import config, CONFIG_FILE_SEARCH_LOCATIONS
from beaker_notebook.lib.utils import import_dotted_class
from beaker_notebook.app.handlers import register_handlers


logger = logging.getLogger("beaker_server")

version = "1.0.0"


class BaseBeakerApp(ServerApp):
    """
    Customizable ServerApp for use with Beaker
    """
    defaults: ClassVar[dict] = {}

    name = traitlets.Unicode("beaker", config=True)
    app_slug = traitlets.Unicode(config=True)

    kernel_manager_class = traitlets.Type(
        f"beaker_notebook.services.kernel.mappingmanager.BeakerKernelMappingManager",
        config=True
    )
    session_manager_class = traitlets.Type(
        f"beaker_notebook.services.session.BeakerSessionManager",
        config=True
    )
    contents_manager_class = traitlets.Type(
        klass=f"beaker_notebook.services.storage.base.BaseBeakerContentsManager",
        default_value=f"beaker_notebook.services.storage.base.BeakerLocalContentsManager",
        config=True,
    )
    kernel_spec_manager_class = traitlets.Type(
        f"beaker_notebook.services.kernel.spec.BeakerKernelSpecManager",
        config=True
    )
    notebook_manager_class = traitlets.Type(
        f"beaker_notebook.services.storage.notebook.BaseNotebookManager",
        # default_value=f"beaker_notebook.services.storage.notebook.FileNotebookManager",
        config=True
    )
    context_manager_class = traitlets.Type(
        f"beaker_notebook.services.context.manager.BeakerContextManager",
        config=True,
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

    disable_check_xsrf = traitlets.Bool(False)
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
        from beaker_notebook.services.auth.notebook import NotebookIdentityProvider
        return NotebookIdentityProvider

    @traitlets.default("authorizer_class")
    def _default_authorizer_class(self):
        from beaker_notebook.services.auth.notebook import NotebookAuthorizer
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
        from beaker_notebook.services.storage.notebook import FileNotebookManager
        return FileNotebookManager

    @traitlets.default("context_manager_class")
    def _default_context_manager_class(self):
        from beaker_notebook.services.context.manager import BeakerContextManager
        return BeakerContextManager

    def __init__(self, **kwargs):
        # Apply defaults from defaults classvar
        defaults = getattr(self.__class__, "defaults", None)

        kwarg_keys = set(self.aliases.keys()) | set(self.flags.keys() | set(self.trait_names()))

        if defaults and isinstance(defaults, dict):
            trait_config = Config(**defaults)
            self.config.update(trait_config)
            kwargs.update({ key: value for key, value in defaults.items() if key in kwarg_keys })

        super().__init__(**kwargs)
        self.handlers = []

    def init_configurables(self, **kwargs):
        # Initialize configurables first to ensure config is loaded before other initializations
        super().init_configurables(**kwargs)

        self.notebook_manager = self.notebook_manager_class(
            parent=self,
        )
        from beaker_notebook.services.context.manager import BeakerContextManager
        self.context_manager: BeakerContextManager = self.context_manager_class(parent=self)

    def initialize(self, argv = None, find_extensions = False, new_httpserver = True, starter_extension = None, **kwargs):
        url_prefix = os.environ.get("BEAKER_SERVER_PREFIX", "").rstrip("/")
        self.base_url = url_prefix

        # Register Beaker-branded error templates ahead of Jupyter's defaults so that
        # 404/500/generic error pages match the Beaker interface instead of the stock
        # Jupyter pages. The jinja FileSystemLoader searches extra_template_paths first.
        error_template_path = os.path.join(os.path.dirname(__file__), "error_templates")
        if error_template_path not in self.extra_template_paths:
            self.extra_template_paths = [*self.extra_template_paths, error_template_path]

        super().initialize(argv, find_extensions, new_httpserver, starter_extension, **kwargs)

        self.config["KernelProvisionerFactory"].setdefault("default_provisioner_name", "beaker-local-provisioner")
        if config.jupyter_token:
            self.config["IdentityProvider"].setdefault("token", config.jupyter_token)

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
        register_handlers(self)
        new_handlers = []
        for handler in self.handlers:
            pattern = url_path_join(self.base_url, handler[0])
            new_handler = (pattern, *list(handler[1:]))
            new_handlers.append(new_handler)
        self.web_app.add_handlers(".*", new_handlers)

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
            if self.config_file_name not in default_config_files:
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
        return {k: v for k, v in autodiscover("extensions").items() if v is not None}

    @traitlets.default('service_user')
    def _default_service_user(self):
        return getpass.getuser()

    @traitlets.default('agent_user')
    def _default_agent_user(self):
        return os.environ.get("BEAKER_AGENT_USER", self.service_user)

    @traitlets.default('subkernel_user')
    def _default_subkernel_user(self):
        return os.environ.get("BEAKER_SUBKERNEL_USER", self.service_user)

    @traitlets.default('working_dir')
    def _default_working_dir(self):
        if self.service_user == "root" and self.subkernel_user != "root":
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

    def stop(self, from_signal = False, **kwargs):
        print("Shutting down Beaker server...")
        return super().stop(from_signal, **kwargs)

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

    def _get_urlparts(self, path: str | None = None, include_token: bool = False, **kwargs) -> urllib.parse.ParseResult:
        # Always return urls without tokens
        return super()._get_urlparts(path, False, **kwargs)

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
            "c = get_config()  # noqa # type: ignore",
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

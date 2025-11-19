import getpass
import logging
import os
import pwd
import shutil
import signal
import urllib.parse

from jupyter_client.ioloop.manager import AsyncIOLoopKernelManager
from jupyter_server.services.kernels.kernelmanager import AsyncMappingKernelManager
from jupyter_server.services.sessions.sessionmanager import SessionManager
from jupyter_server.serverapp import ServerApp
from jupyterlab_server import LabServerApp

from beaker_kernel.lib.app import BeakerApp
from beaker_kernel.lib.config import config
from beaker_kernel.lib.utils import import_dotted_class
from beaker_kernel.service.handlers import register_handlers, SummaryHandler, request_log_handler, sanitize_env

logger = logging.getLogger("beaker_server")
HERE = os.path.dirname(__file__)

version = "1.0.0"


class BeakerKernelManager(AsyncIOLoopKernelManager):

    # Longer wait_time for shutdown before killing processed due to potentially needing to shutdown both the subkernel
    # and the beaker kernel.
    shutdown_wait_time = 10.0

    @property
    def beaker_config(self):
        return getattr(self.parent, 'beaker_config')

    @property
    def app(self) -> "BeakerServerApp":
        return self.parent.parent

    def write_connection_file(self, **kwargs: object) -> None:
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
        # Fetch values from super()
        cmd, kw = await super()._async_pre_start_kernel(**kw)

        env = kw.pop("env", {})

        # Update user, env variables, and home directory based on type of kernel being started.
        if self.kernel_name == "beaker_kernel":
            user = self.app.agent_user
        else:
            env = sanitize_env(env)
            user = self.app.subkernel_user

        user_info = pwd.getpwnam(user)
        home_dir = os.path.expanduser(f"~{user}")
        group_list = os.getgrouplist(user, user_info.pw_gid)
        if user_info.pw_uid != os.getuid():
            env["USER"] = user
            kw["user"] = user
            env["HOME"] = home_dir
        if os.getuid() == 0 or os.geteuid() == 0:
            kw["group"] = user_info.pw_gid
            kw["extra_groups"] = group_list[1:]
        kw["cwd"] = self.app.working_dir

        # Update keyword args that are passed to Popen()
        kw["env"] = env

        return cmd, kw
    pre_start_kernel = _async_pre_start_kernel

    async def _async_interrupt_kernel(self):
        if self.shutting_down and self.kernel_name == "beaker_kernel":
            # During shutdown, interrupt Beaker kernel instances without interrupting the subkernel which is being
            # interrupted/shutdown in parallel by the server.
            # Sending an INTERRUPT signal notifies beaker to interrupt without affecting the subkernel.
            # Normal interrupts are done via a interrupt message, which will also interrupt the subkernel.
            return await self._async_signal_kernel(signal.SIGINT)
        return await super()._async_interrupt_kernel()


class BeakerKernelMappingManager(AsyncMappingKernelManager):
    # kernel_manager_class = BeakerKernelManager
    kernel_manager_class = "beaker_kernel.service.base.BeakerKernelManager"
    connection_dir = os.path.join(config.beaker_run_path, "kernelfiles")

    def __init__(self, **kwargs):
        # Ensure connection dir exists and is readable
        if not os.path.isdir(self.connection_dir):
            os.makedirs(self.connection_dir, mode=0o0755)
        else:
            os.chmod(self.connection_dir, 0o0755)
        super().__init__(**kwargs)

    @property
    def beaker_config(self):
        return getattr(self.parent, 'beaker_config', None)


class BeakerServerApp(ServerApp):
    """
    Customizable ServerApp for use with Beaker
    """

    kernel_manager_class = BeakerKernelMappingManager
    reraise_server_extension_failures = True

    service_user: str
    agent_user: str
    subkernel_user: str
    working_dir: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.service_user = getpass.getuser()
        if self.service_user == "root":
            self.agent_user = os.environ.get("BEAKER_AGENT_USER", None)
            self.subkernel_user = os.environ.get("BEAKER_SUBKERNEL_USER", None)
            if self.agent_user is None or self.subkernel_user is None:
                raise RuntimeError("When running as root, BEAKER_AGENT_USER and BEAKER_SUBKERNEL_USER environment errors must be set.")
            self.working_dir = os.path.expanduser(f"~{self.subkernel_user}")
        else:
            self.agent_user = os.environ.get("BEAKER_AGENT_USER", self.service_user)
            self.subkernel_user = os.environ.get("BEAKER_SUBKERNEL_USER", self.service_user)
            self.working_dir = os.getcwd()

    @property
    def _default_root_dir(self):
        return self.working_dir or super()._default_root_dir()

    def stop(self, from_signal = False):
        print("Shutting down Beaker server...")
        return super().stop(from_signal)

    @property
    def beaker_config(self):
        return getattr(self.starter_app, 'extension_config', None)

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


class BaseBeakerServerApp(LabServerApp):
    name = "beaker_kernel"
    serverapp_class = BeakerServerApp
    load_other_extensions = True
    app_name = "Beaker Jupyter App"
    app_version = version
    allow_origin = "*"
    open_browser = False
    extension_url = "/"
    connection_dir = ""
    log_requests = False

    app_traits = {}
    subcommands = {}

    ui_path = os.path.join(HERE, "ui")

    @classmethod
    def get_extension_package(cls):
        return cls.__module__

    @classmethod
    def initialize_server(cls, argv=None, load_other_extensions=True, **kwargs):
        # Set Jupyter token from config
        os.environ.setdefault("JUPYTER_TOKEN", config.jupyter_token)
        kwargs.update(cls.app_traits)
        app = super().initialize_server(argv=argv, load_other_extensions=load_other_extensions, **kwargs)
        # Log requests to console if configured
        if cls.log_requests:
            app.web_app.settings["log_function"] = request_log_handler
        return app

    def initialize_handlers(self):
        """Bypass initializing the default handler since we don't need to use the webserver, just the websockets."""
        self.handlers.append((r"/summary", SummaryHandler))
        register_handlers(self)
        super().initialize_handlers()

    def initialize_settings(self):
        beaker_app_slug = os.environ.get("BEAKER_APP", None)
        if beaker_app_slug:
            cls: type[BeakerApp] = import_dotted_class(beaker_app_slug)
            beaker_app: BeakerApp = cls()
            self.extension_config["app_cls"] = cls
            self.extension_config["app"] = beaker_app
        else:
            self.extension_config["app_cls"] = None
            self.extension_config["app"] = None


if __name__ == "__main__":
    BeakerServerApp.launch_instance()

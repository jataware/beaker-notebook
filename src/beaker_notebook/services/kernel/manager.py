import os
import pwd
import shutil
import signal
from typing import Optional, TYPE_CHECKING

from traitlets.traitlets import Unicode, Float
from jupyter_client.ioloop.manager import AsyncIOLoopKernelManager

from beaker_notebook.lib.app import BeakerApp
from beaker_notebook.lib.config import config
from beaker_notebook.services.auth import BeakerUser, current_user

if TYPE_CHECKING:
    from beaker_notebook.app.base import BaseBeakerApp


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
        """Get the BaseBeakerApp instance.

        Returns
        -------
        BaseBeakerApp
            The server application instance
        """
        return self.parent.parent

    def setup_instance(self, *args, **kwargs):
        super().setup_instance(*args, **kwargs)
        self.user = kwargs.get("user", None)

    async def _async_start_kernel(self, **kw):
        return await super()._async_start_kernel(**kw)
    start_kernel = _async_start_kernel

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
        kwargs.setdefault("server", self.app.public_url)

        super().write_connection_file(
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

        beaker_user: BeakerUser = current_user.get()

        cmd, kw = await super()._async_pre_start_kernel(**kw)

        env = kw.pop("env", {})

        # Update user, env variables, and home directory based on type of kernel being started.
        if self.kernel_name == "beaker_kernel":
            kernel_user = self.app.agent_user
            home_dir = os.path.expanduser(f"~{kernel_user}")
            kw["cwd"] = home_dir
            env["HOME"] = home_dir
            env = await self.app.secrets_manager.sanitize_kernel_environment_vars(env=env)
        else:
            kernel_user = self.app.subkernel_user
            home_dir = kw.get("cwd")
            env = await self.app.secrets_manager.sanitize_subkernel_envionment_vars(user=beaker_user, env=env)

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

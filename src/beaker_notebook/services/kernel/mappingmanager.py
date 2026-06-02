import os
from typing import TYPE_CHECKING, cast, ClassVar, Any
from collections.abc import Callable

import traitlets
from traitlets import Unicode, Integer
from traitlets.utils.importstring import import_item
from jupyter_server.services.kernels.kernelmanager import AsyncMappingKernelManager

from beaker_notebook.lib.config import config
from beaker_notebook.services.auth import current_user, BeakerUser

from .manager import BeakerKernelManager


class BeakerKernelMappingManager(AsyncMappingKernelManager):

    kernel_manager_class = traitlets.DottedObjectName("beaker_notebook.services.kernel.manager.BeakerKernelManager")
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

    def _create_kernel_manager_factory(self) -> Callable:
        kernel_manager_ctor = import_item(self.kernel_manager_class)

        def create_kernel_manager(*args: Any, **kwargs: Any) -> BeakerKernelManager:
            if self.shared_context:
                if self.context.closed:
                    # recreate context if closed
                    self.context = self._context_default()
                kwargs.setdefault("context", self.context)
            kwargs.setdefault("user", self.get_current_user())
            km = kernel_manager_ctor(*args, **kwargs)
            return km

        return create_kernel_manager

    def __init__(self, **kwargs):
        """Initialize BeakerKernelMappingManager.

        Sets up the connection directory and initializes the kernel manager
        with default kernel name if available.

        Parameters
        ----------
        **kwargs
            Additional arguments passed to parent class
        """
        # If connection_dir is passed in, ignore it in favor of connection_dir value on class.
        kwargs.pop("connection_dir", None)

        # Ensure connection dir exists and is readable
        if not os.path.isdir(self.connection_dir):
            os.makedirs(self.connection_dir, mode=0o0755)
        elif os.stat(self.connection_dir).st_mode & 0o0755 != 0o0755:
            os.chmod(self.connection_dir, 0o0755)
        super().__init__(**kwargs)
        if hasattr(self.kernel_spec_manager, "get_default_kernel_name"):
            self.default_kernel_name = self.kernel_spec_manager.get_default_kernel_name()

    def get_kernel(self, kernel_id: str) -> BeakerKernelManager:
        """Get the single KernelManager object for a kernel by its uuid.

        Parameters
        ==========
        kernel_id : uuid
            The id of the kernel.
        """
        return self._kernels.get(kernel_id, None)

    def is_alive(self, kernel_id):
        km = self.get_kernel(kernel_id)
        if km is None or km.provisioner is None:
            return False
        connection_info = km.get_connection_info()
        if not connection_info:
            return False
        return super().is_alive(kernel_id)

    @property
    def beaker_config(self):
        return getattr(self.parent, 'beaker_config', None)

    def get_current_user(self) -> BeakerUser | None:
        user: BeakerUser = current_user.get() or None
        return user

    def cwd_for_path(self, path, **kwargs):
        user: BeakerUser = current_user.get()
        if isinstance(user, BeakerUser):
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
        beaker_session = kwargs.get('env', {}).get('BEAKER_SESSION', None) or kwargs.get("session_path", None)
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

    def __bool__(self):
        return True

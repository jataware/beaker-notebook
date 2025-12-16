import json
import os
import socket
from typing import TYPE_CHECKING, cast, ClassVar, Any
from collections.abc import Callable
from dataclasses import MISSING

import traitlets
from tornado.ioloop import PeriodicCallback
from traitlets.config.configurable import LoggingConfigurable
from traitlets import Unicode, Integer, Instance, Type, default
from traitlets.utils.importstring import import_item
from jupyter_server.services.kernels.kernelmanager import AsyncMappingKernelManager

from beaker_kernel.lib.config import config
from beaker_kernel.services.auth import current_user, BeakerUser
from beaker_kernel.services.datastore import DatastoreTable
from beaker_kernel.services.datastore.records import TableDict, TableDictRecord

from .manager import BeakerKernelManager, KernelTable, KernelRecord

if TYPE_CHECKING:
    from .manager import BeakerDistributedKernelManager

class BeakerKernelMappingManager(AsyncMappingKernelManager):
    distributed: ClassVar[bool] = False

    kernel_manager_class = traitlets.DottedObjectName("beaker_kernel.services.kernel.manager.BeakerKernelManager")
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
        # Ensure connection dir exists and is readable
        if not os.path.isdir(self.connection_dir):
            os.makedirs(self.connection_dir, mode=0o0755)
        else:
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
        if km.provisioner is None:
            return False
        connection_info = km.get_connection_info()
        if not connection_info:
            return False
        return super().is_alive()

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


class BeakerDistributedKernelMappingManager(BeakerKernelMappingManager):
    distributed = True
    shared_context = False

    kernel_manager_class = traitlets.DottedObjectName("beaker_kernel.services.kernel.manager.BeakerDistributedKernelManager")
    kernel_table_class = Type(
        default_value=KernelTable,
        klass=DatastoreTable,
    )
    kernel_table = Instance(
        klass=DatastoreTable,
    )
    _kernels = Instance(
        klass=TableDict,
    )

    @default("_kernels")
    def _default_kernels(self):
        return TableDict(self.kernel_table, parent=self)

    @default("kernel_table")
    def _default_kernel_table(self):
        return self.kernel_table_class(datastore=self.parent.datastore)

    def get_kernel(self, kernel_id: str) -> BeakerKernelManager|None:
        kernel_record =  self.kernel_table.get(kernel_id=kernel_id)
        if not kernel_record:
            return None
        km = self.kernel_table.deserialize(kernel_record, parent=self)
        return km

    async def _add_kernel_when_ready(self, kernel_id, km: BeakerKernelManager, kernel_awaitable):
        await super()._add_kernel_when_ready(kernel_id, km, kernel_awaitable)
        # Save updates to the kernel manager
        self._kernels[kernel_id] = km


class PeriodicService(LoggingConfigurable):
    frequency_secs: int|None = Integer(None, allow_none=True, config=True)
    enabled: bool = traitlets.Bool(True, config=True)
    run_immediately: bool = traitlets.Bool(False, config=True)

    _pcallback: PeriodicCallback|None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._pcallback = None


    def start(self) -> None:
        """Start the polling of the kernel."""
        if self._pcallback is None:

            if self.frequency_secs is None:
                self.log.info("Not starting periodic service -- frequency_secs is None")
            else:
                self._pcallback = PeriodicCallback(
                    self.fire,
                    1000 * self.frequency_secs,
                )
                self._pcallback.start()
                if self.run_immediately:
                    self.fire()


    def stop(self) -> None:
        """Stop the kernel polling."""
        if self._pcallback is not None:
            self._pcallback.stop()
            self._pcallback = None

    def fire(self, *args, **kwargs):
        raise NotImplementedError()


class DistributedKernelAlivenessCheck(PeriodicService):

    mapping_manager: BeakerDistributedKernelMappingManager = Instance("beaker_kernel.services.kernel.mappingmanager.BeakerKernelMappingManager")

    @traitlets.default("run_immediately")
    def _default_run_immediately(self):
        return True

    async def fire(self, *args, **kwargs):
        kernel_id: str
        km: "BeakerDistributedKernelManager"
        dead_kernels = []
        for kernel_id, km in self.mapping_manager._kernels.items():
            is_alive = await km.is_alive()
            if not is_alive:
                dead_kernels.append(kernel_id)
        for kernel_id in dead_kernels:
            self.mapping_manager.log.info(f"Removing dead kernel {kernel_id} from mapping manager")
            self.mapping_manager.kernel_table.remove(kernel_id=kernel_id)

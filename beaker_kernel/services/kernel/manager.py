import datetime
import json
import os
import pwd
import shutil
import signal
import socket
from pathlib import Path
from typing import Optional, cast, TYPE_CHECKING

import traitlets
from traitlets import Unicode, Integer, Float, Instance, Type, default
from jupyter_client.connect import KernelConnectionInfo
from jupyter_client.ioloop.manager import AsyncIOLoopKernelManager
from jupyter_server.services.kernels.kernelmanager import AsyncMappingKernelManager

from beaker_kernel.lib.app import BeakerApp
from beaker_kernel.lib.config import config
from beaker_kernel.services.auth import current_user, BeakerUser
from beaker_kernel.services.datastore import DatastoreTable, Column, ColumnType

if TYPE_CHECKING:
    from beaker_kernel.app.base import BaseBeakerApp

class KernelTable(DatastoreTable):
    name = "kernels"
    columns = [
        # Identity
        Column(name="kernel_id", column_type=ColumnType.TEXT, primary_key=True),
        Column(name="kernel_name", column_type=ColumnType.TEXT, allow_null=False),  # renamed from 'name'
        Column(name="user_id", column_type=ColumnType.TEXT),

        # Sessions (Beaker-specific)
        Column(name="beaker_session", column_type=ColumnType.TEXT, allow_null=True),
        Column(name="jupyter_session", column_type=ColumnType.TEXT, allow_null=True),

        # Kernel configuration
        Column(name="connection_info", column_type=ColumnType.JSON, allow_null=False),
        Column(name="path", column_type=ColumnType.TEXT),  # API path
        Column(name="cwd", column_type=ColumnType.TEXT, allow_null=True),  # actual working directory

        # State tracking
        Column(name="execution_state", column_type=ColumnType.TEXT, allow_null=False, default_value="starting"),
        Column(name="last_activity", column_type=ColumnType.DATETIME, allow_null=False),
        Column(name="connections", column_type=ColumnType.INTEGER, default_value=0),
        Column(name="reason", column_type=ColumnType.TEXT, allow_null=True),
        Column(name="autorestart", column_type=ColumnType.BOOLEAN, default_value=True),

        # Timestamps
        Column(name="started_at", column_type=ColumnType.DATETIME, allow_null=False),
        Column(name="last_restart_time", column_type=ColumnType.DATETIME, allow_null=True),
        Column(name="restart_count", column_type=ColumnType.INTEGER, default_value=0),

        # Catch-all
        Column(name="metadata", column_type=ColumnType.JSON),
    ]


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

    @classmethod
    def from_record(cls, record):
        """Rehydrates a KernelManager from a record stored in the DB"""
        instance = cls.__init__()
        for k, v in record:
            setattr(instance, k, v)
        return instance

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

    kernel_table_class = Type(
        default_value=KernelTable,
        klass=DatastoreTable,
    )
    kernel_table = Instance(
        klass=DatastoreTable,
    )

    @default("kernel_table")
    def _default_kernel_table(self):
        return self.kernel_table_class(datastore=self.parent.datastore)

    def is_alive(self, kernel_id):
        record = self.kernel_table.get(kernel_id=kernel_id)
        connection_info = record.get("connection_info", None)
        if isinstance(connection_info, str):
            connection_info = json.loads(connection_info)
        kernel_ip = connection_info["ip"]
        control_port = connection_info["control_port"]
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.1)
            try:
                sock.connect((kernel_ip, control_port))
                return True
            except (socket.timeout, ConnectionError, OSError):
                return False
        return True

    async def _add_kernel_when_ready(self, kernel_id, km, kernel_awaitable):
        await super()._add_kernel_when_ready(kernel_id, km, kernel_awaitable)
        record_dict = {
            k: v for k, v in {
                name: getattr(km, name, km.__dict__.get(name, None))
                for name in [col.name for col in self.kernel_table_class.columns]
            }.items()
            if v is not None
        }
        connection_info = json.loads(Path(km.connection_file).read_text())
        record_dict["connection_info"] = connection_info
        now = datetime.datetime.now()
        record_dict["last_activity"] = now
        record_dict["started_at"] = now

        self.kernel_table.add(record_dict)
        self._kernels.pop(kernel_id, None)

    @property
    def _kernels(self):
        records = self.kernel_table.all()
        kms = {}
        dead_kms = []
        for record in records:
            # if not self.is_alive(record["kernel_id"]):
            #     dead_kms.append(record)
            #     continue
            kernel_id = record.pop("kernel_id")
            connection_info: KernelConnectionInfo = json.loads(record["connection_info"])

            km: BeakerKernelManager = self.kernel_manager_factory(
                parent=self,
                log=self.log,
                owns_kernel=False,
            )
            km.load_connection_info(connection_info)
            km.last_activity = datetime.datetime.now(tz=datetime.UTC)
            km.execution_state = "idle"
            km.connections = 1
            km.kernel_id = kernel_id
            km.kernel_name = record["kernel_name"]
            km.ready.set_result(None)

            km.user_id = record["user_id"]
            # km.session = record["jupyter_session"]
            km.reason = record["reason"]
            kms[kernel_id] = km
        return kms

    def __len__(self):
        return self.kernel_table.count()

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

    def _check_kernel_id(self, kernel_id: str) -> None:
        """check that a kernel id is valid"""
        # if kernel_id not in self:
        #     raise KeyError("Kernel with id not found: %s" % kernel_id)
        if not self.kernel_table.count(kernel_id=kernel_id) > 0:
            raise KeyError("Kernel with id not found: %s" % kernel_id)
        # records = self.kernel_table.filter(kernel_id=kernel_id)
        # match records:
        #     case []:
        #         return None
        #     case [record]:
        #         km: BeakerKernelManager = self.kernel_manager_factory(
        #             parent=self,
        #             log=self.log,
        #             owns_kernel=False,
        #             **record
        #         )
        #         return km
        #         # return self.
        #     case [*record_list] if len(record_list) > 1:
        #         # More than one!
        #         return None
        #     case _:
        #         return None

    def get_kernel(self, kernel_id: str) -> BeakerKernelManager:
        """Get the single KernelManager object for a kernel by its uuid.

        Parameters
        ==========
        kernel_id : uuid
            The id of the kernel.
        """
        return self._kernels.get(kernel_id, None)

    @property
    def beaker_config(self):
        return getattr(self.parent, 'beaker_config', None)

    def get_current_user(self) -> BeakerUser | None:
        user: BeakerUser = current_user.get()
        return user

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

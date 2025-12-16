import copy
import datetime
import json
import os
import dill
import pickle
import pwd
import shutil
import signal
import socket
from pathlib import Path
from typing import Self, Optional, cast, TYPE_CHECKING, TypeAlias

import traitlets
from traitlets import Unicode, Integer, Float, Instance, Type, default
from traitlets.utils.importstring import import_item
from jupyter_client.connect import KernelConnectionInfo
from jupyter_client.ioloop.manager import AsyncIOLoopKernelManager
from jupyter_server.services.kernels.kernelmanager import AsyncMappingKernelManager

from beaker_kernel.lib.app import BeakerApp
from beaker_kernel.lib.config import config
from beaker_kernel.services.auth import current_user, BeakerUser
from beaker_kernel.services.datastore import DatastoreTable, Column, ColumnType, TableRecord, Now

if TYPE_CHECKING:
    from beaker_kernel.app.base import BaseBeakerApp
    from beaker_kernel.services.kernel.mappingmanager import BeakerKernelMappingManager
    from beaker_kernel.services.kernel.provisioner import BeakerProvisioner



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

    # def __getstate__(self):
    #     state = super().__getstate__()
    #     del state["_ready"]
    #     del state["_trait_values"]["parent"]
    #     del state["_trait_values"]["kernel_spec_manager"]
    #     del state["_trait_values"]["session"]


    #     return state



class BeakerDistributedKernelManager(BeakerKernelManager):

    async def is_alive(self) -> bool:
        """Check to see if kernel is alive without a local process"""
        connection_info = self.get_connection_info()
        if not connection_info:
            return False

        kernel_ip = connection_info["ip"]
        control_port = connection_info["control_port"]

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.1)
            try:
                sock.connect((kernel_ip, control_port))
                # Socket is closed automatically when exiting the context manager
                return True
            except (socket.timeout, ConnectionError, OSError):
                return False
        return True

    def __getstate__(self):
        """Custom handler to allow serialization"""
        state = super().__getstate__()
        return state



class KernelTable(DatastoreTable):
    resource = BeakerKernelManager
    name = "kernels"
    columns = [
        # Identity
        Column(name="kernel_id", column_type=ColumnType.TEXT, primary_key=True),
        Column(name="kernel_name", column_type=ColumnType.TEXT, allow_null=False),
        Column(name="user_id", column_type=ColumnType.TEXT),

        Column(name="cls", column_type=ColumnType.TEXT, allow_null=False),

        # Serialized setup
        Column(name="provisioner", column_type=ColumnType.JSON),

        # Sessions (Beaker-specific)
        Column(name="beaker_session", column_type=ColumnType.TEXT, allow_null=True),

        # TODO: This is apparently only stored in the connection_file json file.
        Column(name="jupyter_session", column_type=ColumnType.TEXT, allow_null=True),

        # Kernel configuration
        Column(name="connection_info", column_type=ColumnType.JSON, allow_null=False),

        # State tracking
        Column(name="execution_state", column_type=ColumnType.TEXT, allow_null=False, default_value="starting"),
        Column(name="last_activity", column_type=ColumnType.DATETIME, allow_null=True),
        Column(name="connections", column_type=ColumnType.INTEGER, default_value=0),
        Column(name="reason", column_type=ColumnType.TEXT, allow_null=True),
        Column(name="autorestart", column_type=ColumnType.BOOLEAN, default_value=True),

        # Timestamps
        Column(name="started_at", column_type=ColumnType.DATETIME, allow_null=True, default_value=Now()),
        Column(name="restart_count", column_type=ColumnType.INTEGER, default_value=0),

        # Catch-all
        Column(name="metadata", column_type=ColumnType.JSON),
    ]

    def serialize(self, resource: BeakerKernelManager) -> "KernelRecord":
        # Warning: Do not modify the passed resource during serialization as resource is a shared reference.
        connection_info = json.loads(Path(resource.connection_file).read_text())
        if resource.provisioner is not None:
            provisioner = {
                "cls": f"{resource.provisioner.__class__.__module__}.{resource.provisioner.__class__.__name__}",
                "uuid": getattr(resource.provisioner, "uuid", None)
            }
        else:
            provisioner = None
        record = dict(
            kernel_id=resource.kernel_id,
            kernel_name=resource.kernel_name,
            user_id=getattr(getattr(resource, "user", None), "username", None),
            cls=f"{resource.__class__.__module__}.{resource.__class__.__name__}",
            provisioner=provisioner,
            beaker_session=resource.beaker_session,
            jupyter_session=connection_info.get("jupyter_session", None),
            connection_info=connection_info,
            connections=getattr(resource, "connections", 0),
            reason=getattr(resource, "reason", None),
            autorestart=getattr(resource, "autorestart", None),
            restart_count=getattr(resource, "restart_count", None),
            metadata=getattr(resource, "metadata", {}),
        )
        if hasattr(resource, "execution_state"):
            record["execution_state"] = getattr(resource, "execution_state")
        if hasattr(resource, "last_activity"):
            record["last_activity"] = getattr(resource, "last_activity")
        return record

    def deserialize(self, record: "KernelRecord", parent: "BeakerKernelMappingManager") -> BeakerKernelManager:
        km: BeakerKernelManager = parent.kernel_manager_factory(
            parent=parent,
            log=parent.log,
            owns_kernel=True,
        )
        if isinstance(record["connection_info"], str):
            connection_info = json.loads(record["connection_info"])
        elif isinstance(record["connection_info"], dict):
            connection_info = record["connection_info"]
        else:
            connection_info = None

        km.load_connection_info(connection_info)
        km.last_activity = datetime.datetime.now(tz=datetime.UTC)
        km.execution_state = "idle"
        km.connections = 1
        km.kernel_id = record["kernel_id"]
        km.kernel_name = record["kernel_name"]
        km.ready.set_result(None)

        km.user_id = record["user_id"]
        # km.session = record["jupyter_session"]
        km.reason = record["reason"]

        provisioner_info = record.get("provisioner", None)
        if isinstance(provisioner_info, str):
            provisioner_info = json.loads(provisioner_info)
        provisioner = None
        if provisioner_info:
            if "cls" in provisioner_info and "uuid" in provisioner_info:
                try:
                    provisioner_cls: BeakerProvisioner = import_item(provisioner_info["cls"])
                    provisioner = provisioner_cls.get_instance(provisioner_info["uuid"])
                except (ImportError, LookupError):
                    pass
        km.provisioner = provisioner
        return km


KernelRecord: TypeAlias = TableRecord[KernelTable]

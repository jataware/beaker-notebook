import asyncio
import datetime
import json
import os
import dill as pickle
import pwd
import shutil
import signal
import socket
from dataclasses import MISSING
from pathlib import Path
from subprocess import Popen
from typing import Self, Optional, cast, TYPE_CHECKING, ClassVar
from uuid import uuid4
from weakref import WeakValueDictionary

import traitlets
from traitlets import Unicode, Integer, Float, Instance, Type, default
from jupyter_client.connect import KernelConnectionInfo
from jupyter_client.provisioning import LocalProvisioner, KernelProvisionerBase, KernelProvisionerFactory

from beaker_kernel.lib.app import BeakerApp
from beaker_kernel.lib.config import config
from beaker_kernel.services.auth import current_user, BeakerUser
from beaker_kernel.services.datastore import DatastoreTable, Column, ColumnType

class BeakerProvisioner(KernelProvisionerBase):
    instance_registry: ClassVar[WeakValueDictionary[str, Self]] = WeakValueDictionary()
    uuid: str

    def setup_instance(self, *args, **kwargs):
        super().setup_instance(*args, **kwargs)
        self.uuid = uuid4().hex

    @classmethod
    def get_instance(cls, uuid, default=MISSING):
        result = cls.instance_registry.get(uuid, MISSING)
        if result is MISSING:
            if default is not MISSING:
                return default
            else:
                raise LookupError(f"Provisioner with UUID {uuid} not found.")
        else:
            return result

class BeakerLocalProvisioner(LocalProvisioner, BeakerProvisioner):
    """
    :class:`LocalProvisioner` is a concrete class of ABC :py:class:`KernelProvisionerBase`
    and is the out-of-box default implementation used when no kernel provisioner is
    specified in the kernel specification (``kernel.json``).  It provides functional
    parity to existing applications by launching the kernel locally and using
    :class:`subprocess.Popen` to manage its lifecycle.

    This class is intended to be subclassed for customizing local kernel environments
    and serve as a reference implementation for other custom provisioners.
    """

    proc_registry: ClassVar[dict[int, Popen]] = {}

    def setup_instance(self, *args, **kwargs):
        super().setup_instance(*args, **kwargs)
        BeakerLocalProvisioner.instance_registry[self.uuid] = self

    async def launch_kernel(self, cmd, **kwargs):
        result = await super().launch_kernel(cmd, **kwargs)
        km = self.parent
        km_manager = km.parent
        km_manager._kernels[km.kernel_id] = km
        return result


class BeakerProvisionerFactory(KernelProvisionerFactory):
    @default("default_provisioner_name")
    def _default_provisioner_name_default(self) -> str:
        """The default provisioner name."""
        return os.getenv(self.default_provisioner_name_env, "beaker-local-provisioner")

import base64
import json
import logging
import typing
from dataclasses import is_dataclass, asdict

from jupyter_client.jsonutil import json_default
from jupyter_server.base.handlers import JupyterHandler

from beaker_kernel.lib.utils import ensure_async

import tornado

if typing.TYPE_CHECKING:
    from beaker_kernel.services.kernel.manager import BeakerKernelManager, BeakerKernelMappingManager

logger = logging.getLogger(__name__)


class SubkernelHandler(JupyterHandler):
    """
    Base handler for Beaker notebook-related API endpoints.
    """

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json")

    def write(self, chunk):
        if is_dataclass(chunk):
            chunk = asdict(chunk)
        elif isinstance(chunk, list):
            chunk = [asdict(item) if is_dataclass(item) else item for item in chunk]
        if isinstance(chunk, (dict, list)):
            chunk = json.dumps(chunk, default=json_default)
        return super().write(chunk)

    @property
    def kernel_manager(self) -> "BeakerKernelMappingManager":
        kernel_manager = getattr(self.serverapp, "kernel_manager", None)
        if kernel_manager is None:
            raise tornado.web.HTTPError(404, "Notebook manager not found")
        return kernel_manager

    async def head(self, kernel_id=None):
        kernel_manager = self.kernel_manager
        self.write(self.kernel_manager.list_kernel_ids)

    async def get(self, kernel_id=None):
        kernel_manager = self.kernel_manager
        kernel_manager.list_kernel_ids()

        if kernel_id in (None, ""):
            kernel_connections = {
                kernel_id: km.get_connection_info()
                for kernel_id, km in kernel_manager._kernels.items()
            }
            self.write(kernel_connections)
        else:
            km = kernel_manager._kernels.get(kernel_id, None)
            if km is None:
                raise Exception("Not found")
            self.write(km.get_connection_info())


handlers = [
    (r"/subkernels/?(?P<kernel_id>.*)/?$", SubkernelHandler),
]

import os
import os.path
from dataclasses import dataclass
from typing import Any

import traitlets

from jupyter_server.base.handlers import AuthenticatedFileHandler
from jupyter_server.services.contents.manager import ContentsManager
from jupyter_server.services.contents.largefilemanager import AsyncLargeFileManager
from beaker_kernel.service.auth import current_user, BeakerUser, BeakerAuthorizer, BeakerIdentityProvider


def with_hidden_files(func):
    """Decorator to temporarily enable hidden files during a method call."""
    async def wrapper(self, *args, **kwargs):
        orig_allow_hidden = self.contents_manager.allow_hidden
        self.contents_manager.allow_hidden = True
        try:
            result = await func(self, *args, **kwargs)
        finally:
            self.contents_manager.allow_hidden = orig_allow_hidden
        return result
    return wrapper


class BaseBeakerContentsManager(ContentsManager):
    pass


class BeakerLocalContentsHandler(AuthenticatedFileHandler):
    @classmethod
    def get_content(cls, abspath, start = None, end = None):
        return super().get_content(abspath, start, end)

    @classmethod
    def get_absolute_path(cls, root, path):
        return super().get_absolute_path(root, path)

    def parse_url_path(self, url_path):
        os_path = super().parse_url_path(url_path)
        return os.path.join(self.current_user.home_dir, os_path)


class BeakerLocalContentsManager(AsyncLargeFileManager, BaseBeakerContentsManager):

    files_handler_class = BeakerLocalContentsHandler

    def _get_os_path(self, path):
        """Override path resolution to use user-specific home directory.

        Parameters
        ----------
        path : str
            Relative path to resolve

        Returns
        -------
        str
            Absolute path within user's home directory
        """
        user: BeakerUser = current_user.get()
        if user:
            return os.path.join(self.parent.virtual_home_root, user.home_dir, path)
        return super()._get_os_path(path)

    async def _notebook_model(self, path, content=True, require_hash=False):
        """
        Override to include session_id in notebook model.
        """
        model = await super()._notebook_model(path, True, require_hash)
        metadata = model.get("content", {}).get("metadata", {})
        model["session_id"] = metadata.get("beaker", {}).get("session_id", None)
        if not content:
            del model["content"]
            del model["format"]
        return model


class BeakerStorageManager(BaseBeakerContentsManager):
    pass

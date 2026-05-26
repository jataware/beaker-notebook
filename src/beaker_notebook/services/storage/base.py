import json
import os
import os.path
from dataclasses import dataclass
from typing import Any

import traitlets

from jupyter_server.base.handlers import AuthenticatedFileHandler
from jupyter_server.services.contents.manager import ContentsManager
from jupyter_server.services.contents.largefilemanager import AsyncLargeFileManager
from beaker_notebook.services.auth import current_user, BeakerUser, BeakerAuthorizer, BeakerIdentityProvider


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
        if isinstance(self.current_user, BeakerUser):
            return os.path.join(self.current_user.home_dir, os_path)
        else:
            return os_path


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
        if isinstance(user, BeakerUser):
            userdir_path = os.path.join(self.parent.virtual_home_root, user.home_dir)
            if not os.path.isdir(userdir_path):
                os.makedirs(userdir_path, exist_ok=True)
            return os.path.join(userdir_path, path)
        return super()._get_os_path(path)

    async def _notebook_model(self, path, content=True, require_hash=False):
        """
        Override to include session_id in notebook model.
        Schema only needs to be validated if content is True.
        If the content is already loaded, grab the metadata from the loaded content.
        If not, read the file as plaintext and parse to json to avoid unnecesary expensive schema validation.
        """
        model = await super()._notebook_model(path, content=content, require_hash=require_hash)
        if content:
            metadata = model.get("content", {}).get("metadata", {})
        else:
            raw_file = await self._file_model(path=path, format="text", content=True, require_hash=require_hash)
            raw_json = json.loads(raw_file.get("content"))
            metadata = raw_json.get("metadata", {})
        model["session_id"] = metadata.get("beaker", {}).get("session_id", None)
        return model


class BeakerStorageManager(BaseBeakerContentsManager):
    pass

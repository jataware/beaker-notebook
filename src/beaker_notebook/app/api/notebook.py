import datetime
import json
import logging
import typing
import uuid
from dataclasses import is_dataclass, asdict
from queue import Empty

from jupyter_client.jsonutil import json_default
from jupyter_server.base.handlers import JupyterHandler

from beaker_notebook.lib.utils import ensure_async

import tornado

if typing.TYPE_CHECKING:
    from beaker_notebook.services.storage.notebook import BaseNotebookManager, NotebookInfo, NotebookContent

logger = logging.getLogger(__name__)


class NotebookHandler(JupyterHandler):
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
    def notebook_manager(self) -> "BaseNotebookManager":
        notebook_manager = getattr(self.serverapp, "notebook_manager", None)
        if notebook_manager is None:
            raise tornado.web.HTTPError(404, "Notebook manager not found")
        return notebook_manager

    async def head(self, notebook_id=None):
        self.write({})

    async def get(self, notebook_id=None):
        notebook_id = notebook_id or None
        try:
            notebook = await self.notebook_manager.get_notebook(notebook_id)
        except FileNotFoundError:
            notebook = None
        if notebook is None:
            raise tornado.web.HTTPError(404, "Notebook not found")
        self.write(notebook)

    async def post(self, notebook_id=None):
        notebook_id = notebook_id or None
        session = self.get_query_argument("session", None)
        name = self.get_query_argument("name", None)
        body = tornado.escape.json_decode(self.request.body)
        content: "typing.Optional[NotebookContent]" = body.get("content", None)
        if content is None:
            raise tornado.web.HTTPError(400, "No notebook content provided in request body")

        notebook: "NotebookInfo" = await self.notebook_manager.save_notebook(
            content=content,
            notebook_id=notebook_id,
            session=session,
            name=name,
        )
        self.write(notebook)

    async def delete(self, notebook_id=None):
        if not notebook_id:
            raise tornado.web.HTTPError(400, "No notebook ID provided for deletion")
        await self.notebook_manager.delete_notebook(notebook_id)
        self.set_status(204)
        # self.finish()


class SnapshotHandler(JupyterHandler):
    """
    Handler for session based notebook snapshots.
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
    def notebook_manager(self) -> "BaseNotebookManager":
        notebook_manager = getattr(self.serverapp, "notebook_manager", None)
        if notebook_manager is None:
            raise tornado.web.HTTPError(404, "Notebook manager not found")
        return notebook_manager

    def _safe_session_id(self, session_id: str) -> str:
        """Ensure the session id is a single, traversal-free path component.

        The session id is taken straight from the URL and used to build the
        snapshot filename, so reject anything that could escape the snapshot
        directory before it reaches the storage layer.
        """
        if not session_id:
            raise tornado.web.HTTPError(400, "No session ID provided")
        if session_id in (".", "..") or "/" in session_id or "\\" in session_id or "\x00" in session_id:
            raise tornado.web.HTTPError(400, "Invalid session ID")
        return session_id

    async def head(self, session_id=None):
        try:
            snapshots = await self.notebook_manager.list_snapshots()
            self.write(snapshots)
        except Exception:
            self.write({})

    async def get(self, session_id):
        session_id = self._safe_session_id(session_id)
        try:
            notebook = await self.notebook_manager.get_snapshot(session_id)
        except FileNotFoundError:
            notebook = None
        if notebook is None:
            raise tornado.web.HTTPError(404, "Notebook not found")
        self.write(notebook)

    async def post(self, session_id):
        session_id = self._safe_session_id(session_id)
        name = self.get_query_argument("name", None)
        body = tornado.escape.json_decode(self.request.body)
        content: "typing.Optional[NotebookContent]" = body.get("content", None)
        if content is None:
            raise tornado.web.HTTPError(400, "No notebook content provided in request body")

        notebook: "NotebookInfo" = await self.notebook_manager.save_snapshot(
            session_id=session_id,
            content=content,
            name=name,
        )
        self.write(notebook)

    async def delete(self, session_id):
        session_id = self._safe_session_id(session_id)
        await self.notebook_manager.delete_snapshot(session_id)
        self.set_status(204)


handlers = [
    (r"/notebook/snapshot/?(?P<session_id>.*)/?$", SnapshotHandler),
    (r"/notebook/?(?P<notebook_id>.*)/?$", NotebookHandler),
]

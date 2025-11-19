import datetime
import json
import logging
import typing
import uuid
from dataclasses import is_dataclass, asdict
from queue import Empty

from jupyter_client.jsonutil import json_default
from jupyter_server.base.handlers import JupyterHandler

from beaker_kernel.lib.utils import ensure_async

import tornado

if typing.TYPE_CHECKING:
    from beaker_kernel.service.storage.notebook import BaseNotebookManager, NotebookInfo, NotebookContent

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
        session_id = self.get_query_argument("session", None)
        try:
            notebook = await self.notebook_manager.get_notebook(notebook_id, session_id)
        except FileNotFoundError:
            notebook = None
        if notebook is None:
            raise tornado.web.HTTPError(404, "Notebook not found")
        self.write(notebook)
        # if notebook_id:
        #     try:
        #         notebook = await self.notebook_manager.get_notebook(notebook_id)
        #         self.write(notebook)
        #         return
        #     except FileNotFoundError:
        #         raise tornado.web.HTTPError(404, f"Notebook {notebook_id} not found")

        # notebooks = await self.notebook_manager.list_notebooks()

        # If only a single notebook with ID "*", return it directly to allow browser to use alternative storage
        # if len(notebooks) == 1 and notebooks[0].id == "*":
        #     notebooks[0].session_id = session_id
            # return self.write(notebooks[0])

        # if session_id is not None:
        #     for nb in notebooks:
        #         if nb.session_id == session_id:
        #             notebook = await self.notebook_manager.get_notebook(nb.id)
        #             self.write(notebook)
        #     raise tornado.web.HTTPError(404, f"No notebook found for session {session_id}")
        # else:
        #     self.write(notebooks)

    async def post(self, notebook_id=None):
        user = self.get_current_user()
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

    # async def patch(self, notebook_id=None):
    #     body = tornado.escape.json_decode(self.request.body)
    #     self.write({})
    #
    # async def put(self, notebook_id=None):
    #     body = tornado.escape.json_decode(self.request.body)
    #     self.write({})

    async def delete(self, notebook_id=None):
        if not notebook_id:
            raise tornado.web.HTTPError(400, "No notebook ID provided for deletion")
        await self.notebook_manager.delete_notebook(notebook_id)
        self.set_status(204)
        # self.finish()


handlers = [
    (r"/notebook/?(?P<notebook_id>.*)/?$", NotebookHandler),
]

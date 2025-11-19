import os.path
import uuid
from dataclasses import dataclass
from typing import Any, Optional, TypeAlias, Literal

import traitlets
from traitlets.config import Configurable

from jupyter_core.utils import ensure_async
from jupyter_server.services.contents.manager import ContentsManager
from jupyter_server.services.contents.filemanager import AsyncFileContentsManager
from beaker_kernel.service.auth import BeakerUser


def with_hidden_files(func):
    """Decorator to temporarily enable hidden files during a method call."""
    async def wrapper(self, *args, **kwargs):
        orig_allow_hidden = self.contents_manager.allow_hidden
        self.contents_manager.allow_hidden = True
        try:
            result = await ensure_async(func(self, *args, **kwargs))
        finally:
            self.contents_manager.allow_hidden = orig_allow_hidden
        return result
    return wrapper


NotebookContent: TypeAlias = dict[str, Any]
NotebookType: TypeAlias = Literal["notebook", "browserStorage", "other"]

@dataclass
class NotebookInfo:
    id: str
    name: str
    created: str
    last_modified: str
    size: int
    type: NotebookType = "notebook"
    session_id: Optional[str] = None
    content: Optional[NotebookContent] = None


class BaseNotebookManager(Configurable):
    async def get_notebook_info(self, notebook_id: str) -> NotebookInfo:
        raise NotImplementedError()

    async def list_notebooks(self) -> list[NotebookInfo]:
        raise NotImplementedError()

    async def get_notebook(self, notebook_id: Optional[str] = None, session_id: Optional[str] = None) -> Optional[NotebookInfo]:
        raise NotImplementedError()

    async def save_notebook(self, notebook_id: str, content: NotebookContent) -> NotebookInfo:
        raise NotImplementedError()

    async def delete_notebook(self, notebook_id: str) -> None:
        raise NotImplementedError()


class FileNotebookManager(BaseNotebookManager):

    contents_manager_class = traitlets.Type(
        default_value=None,
        klass=ContentsManager,
        allow_none=True,
        config=True,
    )
    contents_manager_params = traitlets.Dict(
        default_value={},
        config=True,
    )
    contents_manager = traitlets.Instance(
        klass=ContentsManager,
        help="Contents manager used by the NotebookManager",
        config=True,
    )
    notebook_path = traitlets.Unicode(
        ".notebooks/",
        help="Base path for storing notebooks, relative to contents manager root",
        config=True,
    )

    @traitlets.default("contents_manager")
    def _default_contents_manager(self):
        if self.contents_manager_class not in (traitlets.Undefined, None, ""):
            return self.contents_manager_class(parent=self, **self.contents_manager_params)
        if getattr(self.parent, "contents_manager", None):
            return self.parent.contents_manager
        else:
            return AsyncFileContentsManager(parent=self.parent)

    @with_hidden_files
    async def _find_notebook(self, notebook_id: str) -> str:
        """Find the file path for a given notebook session ID.

        Parameters
        ----------
        notebook_id : str
            The session ID of the notebook.

        Returns
        -------
        str
            The file path of the notebook.
        """
        path = os.path.join(self.notebook_path, notebook_id)
        if not await ensure_async(self.contents_manager.file_exists(path)):
            raise FileNotFoundError(f"Notebook with session ID {notebook_id} not found")
        return path

    async def get_notebook_info(self, notebook_id: str) -> NotebookInfo:
        """Retrieve notebook metadata for a given session ID.

        Parameters
        ----------
        notebook_id : str
            The session ID of the notebook.

        Returns
        -------
        NotebookInfo
            Metadata about the notebook.
        """

        path = await ensure_async(self._find_notebook(notebook_id))
        notebook = await ensure_async(self.contents_manager.get(
            path,
            content=False
        ))
        return NotebookInfo(
            id=notebook['name'],
            name=notebook['name'],
            created=notebook.get('created', None),
            last_modified=notebook.get('last_modified', None),
            size=notebook.get('size', None),
        )

    @with_hidden_files
    async def list_notebooks(self) -> list[NotebookInfo]:
        """
        List all notebooks managed by this NotebookManager.

        Returns
        -------
        list[NotebookInfo]
            A list of metadata for all notebooks.
        """

        try:
            path = self.notebook_path.format(notebook_id="")
        except KeyError:
            path = self.notebook_path
        if await ensure_async(self.contents_manager.dir_exists(path)):
            files = await ensure_async(self.contents_manager.get(path, content=True))
        else:
            files = {
                "content": []
            }
        return sorted(
            [
                NotebookInfo(
                    id=file['name'],
                    name=file['name'],
                    created=file.get('created', None),
                    last_modified=file.get('last_modified', None),
                    size=file.get('size', None),
                    session_id=file.get('session_id', None),
                )
                for file
                in files.get("content", []) if file['type'] == 'notebook'
            ],
            key=lambda notebook: notebook.last_modified, reverse=True
        )

    @with_hidden_files
    async def get_notebook(
        self,
        notebook_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[NotebookInfo]:
        """
        Retrieve a notebook's content and metadata by its session ID.

        Parameters
        ----------
        notebook_id : str
            The unique ID of the notebook.

        Returns
        -------
        NotebookInfo
            The notebook's metadata and content.
        """
        match notebook_id, session_id:
            case None, None:
                raise ValueError("Either notebook_id or session_id must be provided")
            case str(), _:
                try:
                    path = await ensure_async(self._find_notebook(notebook_id))
                except KeyError:
                    path = self.notebook_path
                file = await ensure_async(self.contents_manager.get(path, content=True))
                notebook = NotebookInfo(
                    id=file['name'],
                    name=file['name'],
                    created=file.get('created', None),
                    last_modified=file.get('last_modified', None),
                    size=file.get('size', None),
                    content=file.get('content', None),
                    session_id=file.get('session_id', None),
                )
                return notebook
            case _, str():
                # Search for notebook with matching session ID
                notebooks = await ensure_async(self.list_notebooks())
                notebook_meta = next(
                    (nb for nb in notebooks if nb.session_id == session_id),
                    None,
                )
                if notebook_meta is None:
                    raise FileNotFoundError(f"No notebook found for session ID {session_id}")
                path = await ensure_async(self._find_notebook(notebook_meta.id))
                file = await ensure_async(self.contents_manager.get(path, content=True))
                notebook = NotebookInfo(
                    id=file['name'],
                    name=file['name'],
                    created=file.get('created', None),
                    last_modified=file.get('last_modified', None),
                    size=file.get('size', None),
                    content=file.get('content', None),
                    session_id=file.get('session_id', None),
                )
                return notebook
            case _:
                raise ValueError("Invalid arguments provided")

    @with_hidden_files
    async def save_notebook(
        self,
        content: NotebookContent,
        notebook_id: Optional[str] = None,
        session: Optional[str] = None,
        name: Optional[str] = None,
    ) -> NotebookInfo:
        """
        Save a notebook's content by its session ID.

        Parameters
        ----------
        notebook_id : str
            The ID of the notebook.
        content : NotebookContent
            The content of the notebook to save.

        Returns
        -------
        NotebookInfo
            The saved notebook's metadata."""
        if session is None:
            session = str(uuid.uuid4())
        if notebook_id is None:
            notebook_id = f"{session}.ipynb"
        if name is None:
            name = notebook_id
        content.setdefault("metadata", {})
        content["metadata"].setdefault("beaker", {})
        content["metadata"]["beaker"]["session_id"] = session
        path = os.path.join(self.notebook_path, notebook_id)
        model = {
            "type": "notebook",
            "content": content,
            "format": "json",
            "session_id": session,
        }
        if not await ensure_async(self.contents_manager.dir_exists(self.notebook_path)):
            await ensure_async(self.contents_manager.new(
                model={
                    "type": "directory",
                },
                path=self.notebook_path
            ))
        if await ensure_async(self.contents_manager.file_exists(path)):
            return await ensure_async(self.contents_manager.save(model=model, path=path))
        else:
            return await ensure_async(self.contents_manager.new(model=model, path=path))



    @with_hidden_files
    async def delete_notebook(self, notebook_id: str) -> None:
        """
        Delete a notebook by its ID.

        Parameters
        ----------
        notebook_id : str
            The ID of the notebook to delete.
        """
        return await ensure_async(self.contents_manager.delete(
            os.path.join(self.notebook_path, notebook_id)
        ))


class BrowserLocalDataNotebookManager(BaseNotebookManager):
    """
    Dummy implementation of notebook manager that stores notebooks in the browser's local storage.
    """

    async def get_notebook_info(self, notebook_id: str) -> NotebookInfo:
        record_id = f"browser-{notebook_id}"
        return NotebookInfo(
            id=record_id,
            name=notebook_id,
            type="browserStorage",
            created="",
            last_modified="",
            size=0,
        )

    async def list_notebooks(self) -> list[NotebookInfo]:
        return [
            NotebookInfo(
                id="*",
                name="*",
                type="browserStorage",
                created="",
                last_modified="",
                size=0,
            )
        ]

    async def get_notebook(
        self,
        notebook_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[NotebookInfo]:
        if notebook_id:
            record_id = f"browser-notebook:{notebook_id}"
        elif session_id:
            record_id = f"browser-session:{session_id}"
        return NotebookInfo(
            id=record_id,
            name=notebook_id,
            type="browserStorage",
            created="",
            last_modified="",
            size=0,
            session_id=session_id,
        )

    async def save_notebook(self, notebook_id: str, content: NotebookContent) -> NotebookInfo:
        raise NotImplementedError("Browser local data notebooks cannot be saved to the server")

    async def delete_notebook(self, notebook_id: str) -> None:
        raise NotImplementedError("Browser local data notebooks cannot be deleted from the server")

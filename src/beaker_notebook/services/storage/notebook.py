import os.path
import pathlib
from dataclasses import dataclass
from typing import Any, Optional, TypeAlias, Literal

import traitlets
from traitlets.config import Configurable

from jupyter_core.utils import ensure_async
from jupyter_server.services.contents.manager import ContentsManager
from jupyter_server.services.contents.filemanager import AsyncFileContentsManager

from beaker_notebook.services.storage import create_directory_tree, with_hidden_files, with_temp_root



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

    notebook_path = traitlets.Unicode(
        ".notebooks",
        help="Base path for storing notebooks when performing a user-initiated save.",
        config=True,
    )
    snapshot_path = traitlets.Unicode(
        help="Base path for storing snapshots, automatically saved versions of the notebook.",
        config=True,
    )

    @traitlets.default("snapshot_path")
    def _default_snapshot_path(self):
        """Default to save snapshots in same directory as user-saved notebooks if not defined on the server application."""
        return os.path.join(self.notebook_path, ".snapshots")

    async def _list_notebooks(self, path) -> list[NotebookInfo]:
        raise NotImplementedError()

    async def _get_notebook(self, path: os.PathLike, filename: str) -> Optional[NotebookInfo]:
        raise NotImplementedError()

    async def _save_notebook(self, path: os.PathLike, filename: str, content: NotebookContent, **kwargs):
        raise NotImplementedError()

    async def _delete_notebook(self, path: os.PathLike, filename: str) -> None:
        raise NotImplementedError()

    async def get_notebook_info(self, notebook_id: str) -> NotebookInfo:
        raise NotImplementedError()

    async def list_notebooks(self) -> list[NotebookInfo]:
        return await self._list_notebooks(path=self.notebook_path)

    async def get_notebook(self, notebook_id: str) -> Optional[NotebookInfo]:
        return await self._get_notebook(path=self.notebook_path, filename=notebook_id)

    async def save_notebook(self, notebook_id: str, content: NotebookContent, **kwargs) -> NotebookInfo:
        return await self._save_notebook(path=self.notebook_path, filename=notebook_id, content=content, **kwargs)

    async def delete_notebook(self, notebook_id: str) -> None:
        return await self._delete_notebook(path=self.notebook_path, filename=notebook_id)

    async def list_snapshots(self) -> list[NotebookInfo]:
        return await self._list_notebooks(path=self.snapshot_path)

    async def get_snapshot(self, session_id: str) -> Optional[NotebookInfo]:
        return await self._get_notebook(path=self.snapshot_path, filename=f"{session_id}.ipynb")

    async def save_snapshot(self,  session_id: str, content: NotebookContent, **kwargs) -> NotebookInfo:
        return await self._save_notebook(path=self.snapshot_path, filename=f"{session_id}.ipynb", content=content, session=session_id, **kwargs)

    async def delete_snapshot(self, session_id: str) -> None:
        return await self._delete_notebook(path=self.snapshot_path, filename=f"{session_id}.ipynb")


class FileNotebookManager(BaseNotebookManager):

    contents_manager_class = traitlets.Type(
        default_value="jupyter_server.services.contents.filemanager.AsyncFileContentsManager",
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

    @traitlets.default("contents_manager")
    def _default_contents_manager(self):
        if self.contents_manager_class not in (traitlets.Undefined, None, ""):
            return self.contents_manager_class(parent=self, **self.contents_manager_params)
        if getattr(self.parent, "contents_manager", None):
            return self.parent.contents_manager
        else:
            return AsyncFileContentsManager(parent=self.parent)

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
        async with with_temp_root(contents_manager= self.contents_manager, root=self.notebook_path):
            path = os.path.join(self.notebook_path, notebook_id)
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
    async def _list_notebooks(self, path) -> list[NotebookInfo]:
        """
        List all notebooks managed by this NotebookManager.

        Returns
        -------
        list[NotebookInfo]
            A list of metadata for all notebooks.
        """
        async with with_temp_root(contents_manager= self.contents_manager, root=path):
            if await ensure_async(self.contents_manager.dir_exists(path)):
                files = await ensure_async(self.contents_manager.get(path, type="directory", content=True))
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
    async def _get_notebook(
        self,
        path: os.PathLike,
        filename: str,
    ) -> Optional[NotebookInfo]:
        """
        Retrieve a notebook's content and metadata by its session ID.

        Parameters
        ----------
        path : os.PathLike
            The location relative to content root or an absolute path that is a subdirectory of
            beaker_notebook.services.storage.BEAKER_LOCAL_DATA_PATH.

        Returns
        -------
        NotebookInfo
            The notebook's metadata and content.
        """
        async with with_temp_root(contents_manager= self.contents_manager, root=path):
            full_path = os.path.join(path, filename)
            if not await ensure_async(self.contents_manager.file_exists(full_path)):
                raise FileNotFoundError(f"Notebook {filename} not found")
            file = await ensure_async(self.contents_manager.get(full_path, content=True))
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

    @with_hidden_files
    async def _save_notebook(
        self,
        path: os.PathLike,
        filename: str,
        content: NotebookContent,
        session: Optional[str] = None,
        **kwargs,
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
            The saved notebook's metadata.
        """
        async with with_temp_root(contents_manager= self.contents_manager, root=path):
            content.setdefault("metadata", {})
            content["metadata"].setdefault("beaker", {})
            if session:
                content["metadata"]["beaker"]["session_id"] = session

            full_path = os.path.join(path, filename)
            model = {
                "type": "notebook",
                "content": content,
                "format": "json",
                "session_id": session,
            }
            await create_directory_tree(self.contents_manager, path)
            if await ensure_async(self.contents_manager.file_exists(full_path)):
                return await ensure_async(self.contents_manager.save(model=model, path=full_path))
            else:
                return await ensure_async(self.contents_manager.new(model=model, path=full_path))

    @with_hidden_files
    async def _delete_notebook(self, path: os.PathLike, filename: str) -> None:
        """
        Delete a notebook by its ID.

        Parameters
        ----------
        filename : str
            The name of the notebook file to delete.
        """
        async with with_temp_root(contents_manager= self.contents_manager, root=path):
            return await ensure_async(self.contents_manager.delete(
                os.path.join(path, filename)
            ))


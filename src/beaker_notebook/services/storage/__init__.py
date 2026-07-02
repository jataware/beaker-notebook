import asyncio
import os
import pathlib
import platformdirs

from jupyter_core.utils import ensure_async
from jupyter_server.services.contents.manager import ContentsManager


BEAKER_LOCAL_DATA_PATH = platformdirs.user_data_path("beaker")


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


temp_root_lock = asyncio.Lock()
class with_temp_root():
    def __init__(self, contents_manager: ContentsManager, root: os.PathLike):
        self.cm = contents_manager
        self.orig_root = None
        self.temp_root = os.path.abspath(os.path.join(root, '..'))

    async def __aenter__(self):
        # Setting trait values directly to avoid calling root_dir's validator which doesn't
        # like what we're doing here.
        await temp_root_lock.acquire()
        try:
            self.orig_root = self.cm.root_dir
            self.cm._trait_values["root_dir"] = self.temp_root
        except BaseException:
            temp_root_lock.release()
            raise

    async def __aexit__(self, exc_type, exc, tb):
        try:
            self.cm._trait_values["root_dir"] = self.orig_root
        finally:
            temp_root_lock.release()


async def create_directory_tree(contents_manager, path) -> None:
    if await ensure_async(contents_manager.dir_exists(str(path))):
        return None

    dirs_to_create = [path, ]
    parents = pathlib.Path(path).parents
    for parent in parents:
        if await ensure_async(contents_manager.dir_exists(str(parent))):
            break
        else:
            dirs_to_create.append(parent)
    for dir in reversed(dirs_to_create):
        try:
            await ensure_async(contents_manager.new(
                model={
                    "type": "directory",
                },
                path=str(dir)
            ))
        except ValueError:
            if not await ensure_async(contents_manager.dir_exists(str(dir))):
                raise   # the mkdir didn't land — this isn't the benign assertion

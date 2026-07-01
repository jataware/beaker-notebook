"""Regression tests for Beaker server-side notebook snapshot storage.

These capture failure modes worked out while moving notebook snapshots off
browser ``localStorage`` and onto the server notebook storage API:

* Session ids arrive verbatim from the request URL and are interpolated into a
  snapshot filename, so ``SnapshotHandler`` must reject anything that could
  traverse out of the snapshot directory.
* ``BeakerLocalContentsManager._get_os_path`` must ``resolve()`` before its
  ``is_relative_to`` containment check. ``is_relative_to`` is purely lexical, so
  without normalizing ``..`` away a crafted absolute path can pass the check and
  still escape ``BEAKER_LOCAL_DATA_PATH``.
* ``with_temp_root`` swaps the contents manager's ``root_dir`` (bypassing its
  validator), so it must restore the original and must *never* leak its global
  lock -- a leaked lock hangs every subsequent snapshot operation in the process.
* ``create_directory_tree`` must create directories more than one level deep
  (which ``ContentsManager.new`` will not), and must swallow *only* the benign
  out-of-root ``is_hidden`` assertion, re-raising everything else.
* ``save``/``get``/``list``/``delete`` snapshot round-trips, including the
  selected-cell value the front end stashes in notebook metadata; and
  ``delete_snapshot`` takes only a session id.
"""

import asyncio
import os
from pathlib import Path

import pytest
import tornado.web
from jupyter_server.services.contents.filemanager import AsyncFileContentsManager

import beaker_notebook.services.storage as storage_pkg
import beaker_notebook.services.storage.base as storage_base
from beaker_notebook.app.api.notebook import SnapshotHandler
from beaker_notebook.services.storage import (
    create_directory_tree,
    temp_root_lock,
    with_temp_root,
)
from beaker_notebook.services.storage.base import BeakerLocalContentsManager
from beaker_notebook.services.storage.notebook import FileNotebookManager


def _notebook(selected_cell=None):
    """A minimal valid ipynb dict, optionally carrying a selected-cell marker."""
    metadata = {}
    if selected_cell is not None:
        metadata["selected_cell"] = selected_cell
    return {
        "cells": [],
        "metadata": metadata,
        "nbformat": 4,
        "nbformat_minor": 5,
    }


@pytest.fixture
def data_path(tmp_path, monkeypatch):
    """Repoint ``BEAKER_LOCAL_DATA_PATH`` at a temp dir.

    Patched in both the package and ``base`` (where ``_get_os_path`` closes over
    the imported name) so the data-path branch resolves to the sandbox.
    """
    monkeypatch.setattr(storage_pkg, "BEAKER_LOCAL_DATA_PATH", tmp_path)
    monkeypatch.setattr(storage_base, "BEAKER_LOCAL_DATA_PATH", tmp_path)
    return tmp_path


@pytest.fixture
def plain_cm(tmp_path):
    """A vanilla contents manager rooted at the temp dir."""
    return AsyncFileContentsManager(root_dir=str(tmp_path))


@pytest.fixture
def local_cm(data_path):
    """A Beaker contents manager rooted at the (sandboxed) data dir."""
    return BeakerLocalContentsManager(root_dir=str(data_path))


@pytest.fixture
def manager(data_path, local_cm):
    """A FileNotebookManager whose snapshot dir is two levels below the data
    root and does not yet exist, so a save must build the tree."""
    return FileNotebookManager(
        contents_manager=local_cm,
        snapshot_path=str(data_path / "notebooks" / ".snapshots"),
        notebook_path=str(data_path / ".notebook"),
    )


class TestSafeSessionId:
    """SnapshotHandler must reject session ids that aren't a single, safe path
    component before they reach the storage layer."""

    @staticmethod
    def _handler():
        # _safe_session_id only touches its argument, so a bare instance built
        # without tornado's RequestHandler.__init__ is sufficient to exercise it.
        return SnapshotHandler.__new__(SnapshotHandler)

    def test_accepts_plain_session_id(self):
        assert self._handler()._safe_session_id("abc-123") == "abc-123"

    @pytest.mark.parametrize(
        "bad",
        ["", ".", "..", "a/b", "a\\b", "x\x00y", "../../etc/passwd"],
    )
    def test_rejects_traversal_and_separators(self, bad):
        with pytest.raises(tornado.web.HTTPError) as excinfo:
            self._handler()._safe_session_id(bad)
        assert excinfo.value.status_code == 400


class TestGetOsPathContainment:
    """_get_os_path must resolve before deciding a path is inside the data dir."""

    def test_path_within_data_dir_is_returned_as_is(self, local_cm, data_path):
        target = str(data_path / "notebooks" / ".snapshots" / "s.ipynb")
        assert local_cm._get_os_path(target) == target

    def test_dotdot_traversal_cannot_escape_data_dir(self, local_cm, data_path):
        # Lexically this path is "under" the data dir, so the pre-resolve()
        # containment check would have returned it verbatim and let the OS
        # resolve the ".." out to /etc/passwd.
        escaping = os.path.join(str(data_path), "notebooks", "../../../../etc/passwd")
        resolved = os.path.realpath(local_cm._get_os_path(escaping))
        assert resolved != "/etc/passwd"
        assert Path(resolved).is_relative_to(os.path.realpath(str(data_path)))


class TestWithTempRoot:
    """The root_dir swap must be reversible, validator-free, and lock-safe."""

    async def test_bypasses_validator_restores_root_and_releases_lock(self, plain_cm, tmp_path):
        original = plain_cm.root_dir
        missing = str(tmp_path / "does" / "not" / "exist")
        async with with_temp_root(contents_manager=plain_cm, root=missing):
            # The root_dir validator would reject a non-existent dir; the swap
            # writes the trait store directly to get around it.
            assert str(plain_cm.root_dir) == missing
            assert temp_root_lock.locked()
        assert plain_cm.root_dir == original
        assert not temp_root_lock.locked()

    async def test_lock_released_and_root_restored_when_body_raises(self, plain_cm, tmp_path):
        original = plain_cm.root_dir
        with pytest.raises(RuntimeError):
            async with with_temp_root(contents_manager=plain_cm, root=str(tmp_path / "x")):
                raise RuntimeError("boom")
        # A leaked lock here would deadlock every later snapshot operation.
        assert not temp_root_lock.locked()
        assert plain_cm.root_dir == original

    async def test_concurrent_blocks_do_not_corrupt_root_dir(self, plain_cm, tmp_path):
        original = plain_cm.root_dir
        observed_own_root = []

        async def worker(name):
            root = str(tmp_path / name)
            async with with_temp_root(contents_manager=plain_cm, root=root):
                # Without the serializing lock, a sibling task could swap
                # root_dir out from under us across this await point.
                await asyncio.sleep(0)
                observed_own_root.append(str(plain_cm.root_dir) == root)

        await asyncio.gather(*(worker(f"r{i}") for i in range(8)))
        assert observed_own_root and all(observed_own_root)
        assert plain_cm.root_dir == original


class TestCreateDirectoryTree:
    """ContentsManager.new only creates one level; create_directory_tree fills
    in the missing parents."""

    async def test_creates_nested_dirs_more_than_one_level_deep(self, plain_cm, tmp_path):
        await create_directory_tree(plain_cm, "a/b/c")
        assert (tmp_path / "a" / "b" / "c").is_dir()

    async def test_idempotent_when_tree_already_exists(self, plain_cm, tmp_path):
        await create_directory_tree(plain_cm, "a/b/c")
        await create_directory_tree(plain_cm, "a/b/c")  # must not raise
        assert (tmp_path / "a" / "b" / "c").is_dir()


class TestSnapshotLifecycle:
    """End-to-end behavior of the snapshot CRUD surface."""

    async def test_save_then_get_round_trips_content(self, manager):
        await manager.save_snapshot(session_id="sess-1", content=_notebook())
        got = await manager.get_snapshot("sess-1")
        assert got.content["nbformat"] == 4

    async def test_selected_cell_metadata_round_trips(self, manager):
        await manager.save_snapshot(
            session_id="sess-1", content=_notebook(selected_cell="cell-xyz")
        )
        got = await manager.get_snapshot("sess-1")
        assert got.content["metadata"]["selected_cell"] == "cell-xyz"

    async def test_save_builds_missing_nested_snapshot_dir(self, manager, data_path):
        # Exercises create_directory_tree across the contents-manager root
        # boundary: building ``notebooks/`` (a parent of the temp root) trips and
        # swallows the benign is_hidden assertion, then ``.snapshots/`` is created
        # cleanly.
        snapshot_dir = data_path / "notebooks" / ".snapshots"
        assert not snapshot_dir.exists()
        await manager.save_snapshot(session_id="sess-1", content=_notebook())
        assert (snapshot_dir / "sess-1.ipynb").is_file()

    async def test_list_snapshots_includes_saved(self, manager):
        await manager.save_snapshot(session_id="sess-1", content=_notebook())
        await manager.save_snapshot(session_id="sess-2", content=_notebook())
        names = {info.name for info in await manager.list_snapshots()}
        assert {"sess-1.ipynb", "sess-2.ipynb"} <= names

    async def test_delete_snapshot_removes_file(self, manager):
        # Also pins delete_snapshot's signature: session id only, no content arg.
        await manager.save_snapshot(session_id="sess-1", content=_notebook())
        await manager.delete_snapshot("sess-1")
        with pytest.raises(FileNotFoundError):
            await manager.get_snapshot("sess-1")

    async def test_get_missing_snapshot_raises_file_not_found(self, manager):
        with pytest.raises(FileNotFoundError):
            await manager.get_snapshot("never-saved")

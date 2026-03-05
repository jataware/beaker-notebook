import datetime
import os
import shutil
from typing import cast

from jupyter_core.utils import ensure_async
from jupyter_server.services.sessions.sessionmanager import SessionManager
from traitlets import default

from beaker_kernel.services.auth import current_user, BeakerUser


class BeakerSessionManager(SessionManager):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sessions: dict[str, dict] = {}

    @property
    def cursor(self):
        return None

    @property
    def connection(self):
        return None

    def close(self):
        return None

    async def prune_sessions(self, all=False) -> int:
        """
        Removes sessions from the session store.

        Parameters
        ----------
        all : bool
            If true, all sessions are removed.
            If false, only sessions without active kernels are removed.

        Returns
        -------
        int
            Number of sessions pruned.
        """
        count = 0
        all_sessions = await self.list_sessions(include_missing=True)
        for session in all_sessions:
            kernel_model = session.get("kernel", None)
            kernel_id = kernel_model and kernel_model.get("id")
            if all or await self.kernel_culled(kernel_id):
                await self.delete_session(session_id=session["id"])
                count += 1
        return count

    async def list_sessions(self, include_missing=False) -> list[dict]:
        """Returns a list of dictionaries containing all the information from
        the session store"""
        result = [await self.session_model(row) for row in self._sessions.values()]
        return result

    def get_kernel_env(
            self,
            path: str|None,
            name: str|None = None
        ):
        """Get environment variables for Beaker kernel sessions.

        Sets up environment variables including session name, Beaker session,
        and user information for kernel execution.

        Parameters
        ----------
        path : str, optional
            Session path
        name : str, optional
            Session name

        Returns
        -------
        dict
            Environment variables for kernel
        """
        # This only sets env variables for the Beaker Kernel, not subkernels.
        if path is not None:
            try:
                beaker_user = path.split(os.path.sep)[0]
            except Exception:
                beaker_user = None
        else:
            beaker_user = None

        env = {
            **os.environ,
            "JPY_SESSION_NAME": path,
            "BEAKER_SESSION": str(name),
        }
        if beaker_user:
            env.update({
                "BEAKER_USER": beaker_user,
                "LANGSMITH_BEAKER_USER": beaker_user,
            })

        return env

    async def start_kernel_for_session(self, session_id, path, name, type, kernel_name):
        """Start a kernel for a session with user-specific path and permissions.

        For Beaker kernels, sets up user-specific home directories and proper
        file permissions for the subkernel user.

        Parameters
        ----------
        session_id : str
            Unique identifier for the session
        path : str
            Path for the session
        name : str
            Session name
        type : str
            Session type
        kernel_name : str
            Name of the kernel to start

        Returns
        -------
        str
            Kernel ID
        """
        user: BeakerUser = current_user.get()
        if isinstance(user, BeakerUser):
            virtual_home_root = self.parent.virtual_home_root
            virtual_home_dir = os.path.join(virtual_home_root, user.home_dir)

            subkernel_user = self.parent.subkernel_user
            if not os.path.isdir(virtual_home_dir):
                os.makedirs(virtual_home_dir, exist_ok=True)
                if subkernel_user != self.parent.service_user:
                    shutil.chown(virtual_home_dir, user=subkernel_user, group=subkernel_user)
            path = os.path.relpath(virtual_home_dir, self.kernel_manager.root_dir)

        kernel_env = self.get_kernel_env(path, name)
        kernel_id = await self.kernel_manager.start_kernel(
            path=path,
            kernel_name=kernel_name,
            env=kernel_env,
        )
        return cast(str, kernel_id)

    async def session_model(self, session_dict: dict):
        try:
            kernel_model = await ensure_async(self.kernel_manager.kernel_model(session_dict["kernel_id"]))
        except KeyError:
            kernel_model = None

        session_id = session_dict.get("id", session_dict.get("session_id"))
        model = {
            "id": session_id,
            **session_dict,
            "kernel": kernel_model,
        }
        if session_dict["type"] == "notebook":
            # Provide the deprecated API.
            model["notebook"] = {"path": session_dict["path"], "name": session_dict["name"]}
        return model

    async def row_to_model(self, row, tolerate_culled=False):
        return await ensure_async(self.session_model(row))

    async def session_exists(self, path):
        return any(s["path"] == path for s in self._sessions.values())

    async def get_session(self, **kwargs):
        if not kwargs:
            msg = "must specify a column to query"
            raise TypeError(msg)

        for session in self._sessions.values():
            if all(session.get(k) == v for k, v in kwargs.items()):
                return await ensure_async(self.session_model(session))

        from tornado import web
        q = [f"{key}={value}" for key, value in kwargs.items()]
        raise web.HTTPError(404, "Session not found: %s" % (", ".join(q)))

    async def save_session(self, session_id, **kwargs):
        """Saves the items for the session with the given session_id

        Given a session_id (and any other of the arguments), this method
        stores the information for a session in memory.

        Parameters
        ----------
        session_id : str
            uuid for the session; this method must be given a session_id
        path : str
            the path for the given session
        name : str
            the name of the session
        type : str
            the type of the session
        kernel_id : str
            a uuid for the kernel associated with this session

        Returns
        -------
        model : dict
            a dictionary of the session model
        """
        self._sessions[session_id] = {"session_id": session_id, "started_at": datetime.datetime.now(), **kwargs}
        result = await self.get_session(session_id=session_id)
        return result

    async def update_session(self, session_id, **kwargs):
        """Updates the values in the session store.

        Changes the values of the session with the given session_id
        with the values from the keyword arguments.

        Parameters
        ----------
        session_id : str
            a uuid that identifies a session
        **kwargs : str
            the key must correspond to a session field,
            and the value replaces the current value in the session
            with session_id.
        """
        if not kwargs:
            # no changes
            return

        await self.get_session(session_id=session_id)
        self._sessions[session_id].update(kwargs)
        if hasattr(self.kernel_manager, "update_env"):
            row = self._sessions[session_id]
            self.kernel_manager.update_env(kernel_id=row["kernel_id"], env=self.get_kernel_env(row["path"], row["name"]))

    async def delete_session(self, session_id=None):
        """Delete a session and shut down its kernel."""
        session = await self.get_session(session_id=session_id)
        kernel_id = session["kernel"]["id"] if session.get("kernel") else None
        if kernel_id:
            await ensure_async(self.kernel_manager.shutdown_kernel(kernel_id))
        self._sessions.pop(session_id, None)

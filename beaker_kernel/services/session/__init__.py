import datetime
import os
import shutil
from typing import cast

from jupyter_core.utils import ensure_async
from jupyter_server.services.sessions.sessionmanager import SessionManager
from traitlets import Type, Instance, default, validate

from beaker_kernel.services.auth import current_user, BeakerUser
from beaker_kernel.services.datastore import DatastoreTable, Column, ColumnType

class SessionTable(DatastoreTable):
    name = "sessions"
    columns = [
        Column(name="session_id", column_type=ColumnType.TEXT),
        Column(name="path", column_type=ColumnType.TEXT),
        Column(name="name", column_type=ColumnType.TEXT),
        Column(name="type", column_type=ColumnType.TEXT),
        Column(name="kernel_id", column_type=ColumnType.TEXT),
        Column(name="user_id", column_type=ColumnType.TEXT),
        Column(name="started_at", column_type=ColumnType.DATETIME, allow_null=False),
        Column(name="metadata", column_type=ColumnType.JSON),
    ]

class BeakerSessionManager(SessionManager):

    session_table_class = Type(
        default_value=SessionTable,
        klass=DatastoreTable,
    )
    session_table = Instance(
        klass=DatastoreTable,
    )

    @default("session_table")
    def _default_session_table(self) -> SessionTable:
        table: SessionTable = self.session_table_class(datastore=self.parent.datastore)
        self.session_table = table
        return table

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
        return await super().list_sessions()


    def get_kernel_env(self, path, name = None):
        """Get environment variables for Beaker kernel sessions.

        Sets up environment variables including session name, Beaker session,
        and user information for kernel execution.

        Parameters
        ----------
        path : str
            Session path
        name : str, optional
            Session name

        Returns
        -------
        dict
            Environment variables for kernel
        """
        # This only sets env variables for the Beaker Kernel, not subkernels.
        try:
            beaker_user = path.split(os.path.sep)[0]
        except:
            pass
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
        dict
            Session information from parent class
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
        # """Takes sqlite database session row and turns it into a dictionary"""
        # kernel_culled: bool = await ensure_async(self.kernel_culled(row["kernel_id"]))
        # if kernel_culled:
        #     # The kernel was culled or died without deleting the session.
        #     # We can't use delete_session here because that tries to find
        #     # and shut down the kernel - so we'll delete the row directly.
        #     #
        #     # If caller wishes to tolerate culled kernels, log a warning
        #     # and return None.  Otherwise, raise KeyError with a similar
        #     # message.
        #     self.session_table.remove(session_id=row["session_id"])
        #     msg = (
        #         "Kernel '{kernel_id}' appears to have been culled or died unexpectedly, "
        #         "invalidating session '{session_id}'. The session has been removed.".format(
        #             kernel_id=row["kernel_id"], session_id=row["session_id"]
        #         )
        #     )
        #     if tolerate_culled:
        #         self.log.warning(f"{msg}  Continuing...")
        #         return None
        #     raise KeyError(msg)
        return await ensure_async(self.session_model(row))

    async def session_exists(self, path):
        session_list = self.session_table.filter(path=path)
        return bool(session_list)

    async def list_sessions(self):
        """Returns a list of dictionaries containing all the information from
        the session database"""
        result = [await self.session_model(row) for row in self.session_table.all()]
        return result

    async def get_session(self, **kwargs):
        if not kwargs:
            msg = "must specify a column to query"
            raise TypeError(msg)

        results = self.session_table.filter(**kwargs)
        row = next(iter(results), None)

        if row is None:
            from tornado import web
            q = [f"{key}={value}" for key, value in kwargs]
            raise web.HTTPError(404, "Session not found: %s" % (", ".join(q)))

        return await ensure_async(self.session_model(row))

    async def save_session(self, session_id, **kwargs):
        """Saves the items for the session with the given session_id

        Given a session_id (and any other of the arguments), this method
        creates a row in the sqlite session database that holds the information
        for a session.

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
        self.session_table.add({"session_id": session_id, "started_at": datetime.datetime.now(), **kwargs})
        result = await self.get_session(session_id=session_id)
        return result

    async def update_session(self, session_id, **kwargs):
        """Updates the values in the session database.

        Changes the values of the session with the given session_id
        with the values from the keyword arguments.

        Parameters
        ----------
        session_id : str
            a uuid that identifies a session in the sqlite3 database
        **kwargs : str
            the key must correspond to a column title in session database,
            and the value replaces the current value in the session
            with session_id.
        """

        if not kwargs:
            # no changes
            return

        await self.get_session(session_id=session_id)
        self.session_table.update(conditions={"session_id": session_id}, record=kwargs)
        if hasattr(self.kernel_manager, "update_env"):
            row = self.session_table.get(session_id=session_id)
            self.kernel_manager.update_env(kernel_id=row["kernel_id"], env=self.get_kernel_env(row["path"], row["name"]))

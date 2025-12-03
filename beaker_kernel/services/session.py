import os
import shutil
from typing import cast

from jupyter_server.services.sessions.sessionmanager import SessionManager

from beaker_kernel.services.auth import current_user, BeakerUser


class BeakerSessionManager(SessionManager):

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
        if user:
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
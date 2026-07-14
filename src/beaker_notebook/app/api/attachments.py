from __future__ import annotations

import asyncio
import json
from typing import Any

from jupyter_server.base.handlers import JupyterHandler
from tornado import web

from beaker_notebook.services.attachments import AttachmentError, SessionAttachmentManager
from beaker_notebook.services.auth import BeakerUser


class SessionAttachmentHandler(JupyterHandler):
    """Upload, list, inspect, and remove temporary chat attachments."""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json")

    def write_error(self, status_code: int, **kwargs):
        message = self._reason
        exception = kwargs.get("exc_info", (None, None, None))[1]
        if isinstance(exception, web.HTTPError) and exception.log_message:
            message = exception.log_message
        self.finish(json.dumps({"status": status_code, "message": message}))

    @property
    def attachment_manager(self) -> SessionAttachmentManager:
        manager = getattr(self.serverapp, "attachment_manager", None)
        if manager is None:
            raise web.HTTPError(503, "Session attachment storage is unavailable")
        return manager

    def _authenticated_request_kernel_id(self) -> str | None:
        header = self.request.headers.get(self.identity_provider.beaker_kernel_header)
        if not header:
            return None

        kernel_id = self.identity_provider.authenticated_beaker_kernel_id(self)
        if kernel_id is None:
            raise web.HTTPError(403, "Invalid kernel authentication")
        return kernel_id

    async def _resolve_session(self, session_id: str) -> tuple[dict[str, Any], Any, str | None]:
        if not session_id or session_id in (".", "..") or "\x00" in session_id:
            raise web.HTTPError(400, "Invalid session ID")
        try:
            session = await self.session_manager.get_session(path=session_id)
        except web.HTTPError as err:
            if err.status_code == 404:
                raise web.HTTPError(404, "Session not found") from err
            raise

        kernel_id = session.get("kernel", {}).get("id") if session.get("kernel") else session.get("kernel_id")
        kernel_manager = self.kernel_manager.get_kernel(kernel_id) if kernel_id else None
        owner = getattr(kernel_manager, "user", None)

        request_kernel_id = self._authenticated_request_kernel_id()
        if request_kernel_id:
            if request_kernel_id != kernel_id:
                raise web.HTTPError(403, "Kernel does not own this session")
            return session, owner, request_kernel_id

        current = self.current_user
        if isinstance(owner, BeakerUser) and isinstance(current, BeakerUser):
            if owner.username != current.username:
                raise web.HTTPError(403, "Session does not belong to the current user")
        return session, owner or current, None

    def _write_json(self, value: Any) -> None:
        self.write(json.dumps(value))

    async def get(self, session_id: str, attachment_id: str | None = None):
        _, owner, request_kernel_id = await self._resolve_session(session_id)
        try:
            if attachment_id:
                result = await asyncio.to_thread(
                    self.attachment_manager.get_attachment, session_id, attachment_id, owner
                )
            else:
                current_ids = self.get_arguments("current") if request_kernel_id else []
                if request_kernel_id:
                    result = await asyncio.to_thread(
                        self.attachment_manager.commit_attachments,
                        session_id,
                        current_ids,
                        owner,
                    )
                else:
                    result = await asyncio.to_thread(
                        self.attachment_manager.list_attachments, session_id, owner
                    )
        except AttachmentError as err:
            raise web.HTTPError(404, str(err)) from err
        self._write_json(result)

    async def post(self, session_id: str, attachment_id: str | None = None):
        if attachment_id:
            raise web.HTTPError(405)
        _, owner, _ = await self._resolve_session(session_id)
        uploads = self.request.files.get("file", [])
        if len(uploads) != 1:
            raise web.HTTPError(400, "Upload exactly one file per request")
        upload = uploads[0]
        try:
            result = await asyncio.to_thread(
                self.attachment_manager.create_attachment,
                session_id,
                upload.get("filename", "upload"),
                upload.get("content_type"),
                upload.get("body", b""),
                owner,
            )
        except AttachmentError as err:
            raise web.HTTPError(400, str(err)) from err
        self.set_status(201)
        self._write_json(result)

    async def delete(self, session_id: str, attachment_id: str | None = None):
        _, owner, _ = await self._resolve_session(session_id)
        if not attachment_id:
            await asyncio.to_thread(
                self.attachment_manager.delete_session, session_id, owner
            )
            self.set_status(204)
            self.finish()
            return
        try:
            await asyncio.to_thread(
                self.attachment_manager.delete_attachment, session_id, attachment_id, owner
            )
        except AttachmentError as err:
            raise web.HTTPError(404, str(err)) from err
        self.set_status(204)
        self.finish()


handlers = [
    (
        r"attachments/(?P<session_id>[^/]+)/?(?P<attachment_id>[0-9a-fA-F-]+)?",
        SessionAttachmentHandler,
    ),
]

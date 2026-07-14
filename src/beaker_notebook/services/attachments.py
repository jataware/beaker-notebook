from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
import stat
import threading
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from beaker_notebook.lib.config import config
from beaker_notebook.services.auth import BeakerUser


class AttachmentError(ValueError):
    """A user-facing attachment validation or storage error."""


@dataclass(frozen=True)
class AttachmentLimits:
    max_upload_bytes: int = 25 * 1024 * 1024
    max_session_bytes: int = 250 * 1024 * 1024
    max_extracted_bytes: int = 100 * 1024 * 1024
    max_archive_entries: int = 1000
    max_archive_ratio: int = 100

    @classmethod
    def from_config(cls) -> "AttachmentLimits":
        return cls(
            max_upload_bytes=int(config.attachment_max_upload_bytes),
            max_session_bytes=int(config.attachment_max_session_bytes),
            max_extracted_bytes=int(config.attachment_max_extracted_bytes),
            max_archive_entries=int(config.attachment_max_archive_entries),
            max_archive_ratio=int(config.attachment_max_archive_ratio),
        )


class SessionAttachmentManager:
    """Stores temporary chat attachments in a hidden, session-scoped directory."""

    METADATA_FILENAME = "attachment.json"

    def __init__(self, parent: Any, limits: AttachmentLimits | None = None):
        self.parent = parent
        self.limits = limits or AttachmentLimits.from_config()
        self.instance_id = uuid.uuid4().hex
        self._instance_roots: set[Path] = set()
        self._mutation_lock = threading.RLock()

    @staticmethod
    def _safe_filename(filename: str) -> str:
        filename = (filename or "upload").replace("\\", "/")
        basename = PurePosixPath(filename).name.strip().replace("\x00", "")
        if basename in ("", ".", ".."):
            return "upload"
        return basename

    @staticmethod
    def _session_key(session_id: str) -> str:
        return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]

    def _user_root(self, user: Any = None) -> Path:
        if isinstance(user, BeakerUser) and user.home_dir:
            return (Path(self.parent.virtual_home_root) / user.home_dir).resolve()
        return Path(self.parent.root_dir).resolve()

    def _session_root(self, session_id: str, user: Any = None) -> Path:
        instance_root = self._user_root(user) / ".beaker" / "session-attachments" / self.instance_id
        self._instance_roots.add(instance_root)
        return instance_root / self._session_key(session_id)

    def _attachment_root(self, session_id: str, attachment_id: str, user: Any = None) -> Path:
        try:
            normalized_id = str(uuid.UUID(attachment_id))
        except (ValueError, TypeError, AttributeError) as err:
            raise AttachmentError("Invalid attachment ID") from err
        return self._session_root(session_id, user) / normalized_id

    @staticmethod
    def _metadata_path(attachment_root: Path) -> Path:
        return attachment_root / SessionAttachmentManager.METADATA_FILENAME

    def _read_metadata(self, attachment_root: Path) -> dict[str, Any]:
        try:
            return json.loads(self._metadata_path(attachment_root).read_text())
        except (FileNotFoundError, json.JSONDecodeError) as err:
            raise AttachmentError("Attachment not found") from err

    def list_attachments(self, session_id: str, user: Any = None) -> list[dict[str, Any]]:
        session_root = self._session_root(session_id, user)
        if not session_root.is_dir():
            return []
        attachments: list[dict[str, Any]] = []
        for child in session_root.iterdir():
            if not child.is_dir():
                continue
            try:
                metadata = self._read_metadata(child)
            except AttachmentError:
                continue
            if metadata.get("session_id") == session_id:
                attachments.append(metadata)
        attachments.sort(key=lambda item: item.get("created_at", ""))
        return attachments

    def get_attachment(self, session_id: str, attachment_id: str, user: Any = None) -> dict[str, Any]:
        root = self._attachment_root(session_id, attachment_id, user)
        metadata = self._read_metadata(root)
        if metadata.get("session_id") != session_id:
            raise AttachmentError("Attachment not found")
        return metadata

    def commit_attachments(
        self, session_id: str, attachment_ids: list[str], user: Any = None
    ) -> list[dict[str, Any]]:
        """Mark attachments as sent, then return all sent attachments for the session."""
        with self._mutation_lock:
            return self._commit_attachments(session_id, attachment_ids, user)

    def _commit_attachments(
        self, session_id: str, attachment_ids: list[str], user: Any = None
    ) -> list[dict[str, Any]]:
        requested = set(attachment_ids)
        attachments = self.list_attachments(session_id, user)
        available = {item.get("id") for item in attachments}
        missing = requested - available
        if missing:
            raise AttachmentError(f"Attachments are no longer available: {sorted(missing)}")

        for metadata in attachments:
            if metadata.get("id") not in requested or metadata.get("committed"):
                continue
            metadata["committed"] = True
            root = self._attachment_root(session_id, metadata["id"], user)
            self._metadata_path(root).write_text(json.dumps(metadata, indent=2))
        return [item for item in attachments if item.get("committed") or item.get("id") in requested]

    def _session_stored_size(self, session_id: str, user: Any = None) -> int:
        return sum(int(item.get("stored_size", item.get("size", 0))) for item in self.list_attachments(session_id, user))

    @staticmethod
    def _is_zip(filename: str, mimetype: str) -> bool:
        return filename.lower().endswith(".zip") or mimetype in {
            "application/zip",
            "application/x-zip-compressed",
        }

    def _validate_zip_members(self, archive: zipfile.ZipFile) -> tuple[list[zipfile.ZipInfo], int]:
        files: list[zipfile.ZipInfo] = []
        seen_paths: set[str] = set()
        total_size = 0
        total_compressed = 0

        for info in archive.infolist():
            raw_name = info.filename.replace("\\", "/")
            path = PurePosixPath(raw_name)
            if not raw_name or raw_name.startswith("/") or path.is_absolute() or ".." in path.parts:
                raise AttachmentError(f"ZIP contains an unsafe path: {info.filename!r}")
            normalized = path.as_posix().rstrip("/")
            if not normalized:
                continue
            if normalized in seen_paths:
                raise AttachmentError(f"ZIP contains a duplicate path: {normalized!r}")
            seen_paths.add(normalized)

            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise AttachmentError(f"ZIP contains a symbolic link: {normalized!r}")
            if info.flag_bits & 0x1:
                raise AttachmentError("Encrypted ZIP files are not extracted automatically")
            if info.is_dir():
                continue
            if stat.S_IFMT(mode) and not stat.S_ISREG(mode):
                raise AttachmentError(f"ZIP contains a special file: {normalized!r}")

            files.append(info)
            total_size += int(info.file_size)
            total_compressed += int(info.compress_size)

        if len(files) > self.limits.max_archive_entries:
            raise AttachmentError(
                f"ZIP contains {len(files)} files; the limit is {self.limits.max_archive_entries}"
            )
        if total_size > self.limits.max_extracted_bytes:
            raise AttachmentError(
                f"ZIP expands to {total_size} bytes; the limit is {self.limits.max_extracted_bytes}"
            )
        ratio = total_size / max(total_compressed, 1)
        if ratio > self.limits.max_archive_ratio:
            raise AttachmentError(
                f"ZIP compression ratio is {ratio:.1f}:1; the limit is {self.limits.max_archive_ratio}:1"
            )
        return files, total_size

    def _extract_zip(self, archive_path: Path, destination: Path) -> tuple[list[str], int]:
        temporary = destination.with_name(f"{destination.name}.extracting")
        shutil.rmtree(temporary, ignore_errors=True)
        temporary.mkdir(parents=True)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                members, expected_size = self._validate_zip_members(archive)
                extracted_size = 0
                manifest: list[str] = []
                for info in members:
                    relative = PurePosixPath(info.filename.replace("\\", "/"))
                    target = temporary.joinpath(*relative.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open("xb") as output:
                        while chunk := source.read(1024 * 1024):
                            extracted_size += len(chunk)
                            if extracted_size > self.limits.max_extracted_bytes:
                                raise AttachmentError("ZIP exceeded the extracted-size limit while unpacking")
                            output.write(chunk)
                    manifest.append(relative.as_posix())
                if extracted_size != expected_size:
                    raise AttachmentError("ZIP contents did not match the declared uncompressed size")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary.replace(destination)
            return manifest, extracted_size
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    def create_attachment(
        self,
        session_id: str,
        filename: str,
        mimetype: str | None,
        body: bytes,
        user: Any = None,
    ) -> dict[str, Any]:
        with self._mutation_lock:
            return self._create_attachment(session_id, filename, mimetype, body, user)

    def _create_attachment(
        self,
        session_id: str,
        filename: str,
        mimetype: str | None,
        body: bytes,
        user: Any = None,
    ) -> dict[str, Any]:
        if not body:
            raise AttachmentError("The uploaded file is empty")
        if len(body) > self.limits.max_upload_bytes:
            raise AttachmentError(
                f"File is {len(body)} bytes; the per-file limit is {self.limits.max_upload_bytes}"
            )
        if self._session_stored_size(session_id, user) + len(body) > self.limits.max_session_bytes:
            raise AttachmentError("This upload would exceed the session attachment storage limit")

        attachment_id = str(uuid.uuid4())
        safe_name = self._safe_filename(filename)
        resolved_mimetype = mimetype or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
        attachment_root = self._attachment_root(session_id, attachment_id, user)
        attachment_root.mkdir(parents=True, exist_ok=False)

        is_zip = self._is_zip(safe_name, resolved_mimetype)
        original_path: Path | None = None
        file_path: Path | None = None
        root_path = attachment_root / "files"
        archive_status: str | None = None
        archive_error: str | None = None
        manifest: list[str] = []
        extracted_size = 0

        try:
            if is_zip:
                original_path = attachment_root / "original" / safe_name
                original_path.parent.mkdir(parents=True)
                original_path.write_bytes(body)
                archive_status = "extracted"
                try:
                    manifest, extracted_size = self._extract_zip(original_path, root_path)
                    if self._session_stored_size(session_id, user) + len(body) + extracted_size > self.limits.max_session_bytes:
                        raise AttachmentError("Extracted ZIP would exceed the session attachment storage limit")
                except Exception as err:
                    shutil.rmtree(root_path, ignore_errors=True)
                    root_path.mkdir(parents=True, exist_ok=True)
                    archive_status = "failed"
                    archive_error = str(err)
                    manifest = []
                    extracted_size = 0
            else:
                root_path.mkdir(parents=True)
                file_path = root_path / safe_name
                file_path.write_bytes(body)
                manifest = [safe_name]

            stored_size = len(body) + extracted_size
            metadata = {
                "id": attachment_id,
                "session_id": session_id,
                "name": safe_name,
                "mimetype": resolved_mimetype,
                "size": len(body),
                "stored_size": stored_size,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "committed": False,
                "kind": "archive" if is_zip else "file",
                "path": str(file_path.resolve()) if file_path else None,
                "root_path": str(root_path.resolve()),
                "original_path": str(original_path.resolve()) if original_path else None,
                "archive_status": archive_status,
                "archive_error": archive_error,
                "file_count": len(manifest),
                "files": manifest,
            }
            self._metadata_path(attachment_root).write_text(json.dumps(metadata, indent=2))
            return metadata
        except Exception:
            shutil.rmtree(attachment_root, ignore_errors=True)
            raise

    def delete_attachment(self, session_id: str, attachment_id: str, user: Any = None) -> None:
        with self._mutation_lock:
            self._delete_attachment(session_id, attachment_id, user)

    def _delete_attachment(self, session_id: str, attachment_id: str, user: Any = None) -> None:
        attachment_root = self._attachment_root(session_id, attachment_id, user)
        metadata = self._read_metadata(attachment_root)
        if metadata.get("session_id") != session_id:
            raise AttachmentError("Attachment not found")
        shutil.rmtree(attachment_root)

    def delete_session(self, session_id: str, user: Any = None) -> None:
        with self._mutation_lock:
            shutil.rmtree(self._session_root(session_id, user), ignore_errors=True)

    def cleanup(self) -> None:
        """Remove every temporary attachment directory created by this server runtime."""
        with self._mutation_lock:
            attachment_parents = {instance_root.parent for instance_root in self._instance_roots}
            for instance_root in self._instance_roots:
                shutil.rmtree(instance_root, ignore_errors=True)
            self._instance_roots.clear()
            for attachment_parent in attachment_parents:
                try:
                    attachment_parent.rmdir()
                    attachment_parent.parent.rmdir()
                except OSError:
                    # Another server runtime or another .beaker service still owns this directory.
                    pass

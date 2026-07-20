import hashlib
import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tornado import web

from beaker_notebook.app.api.attachments import SessionAttachmentHandler
from beaker_notebook.kernel import BeakerKernel
from beaker_notebook.services.attachments import (
    AttachmentError,
    AttachmentLimits,
    SessionAttachmentManager,
)
from beaker_notebook.services.auth import BeakerIdentityProvider


@pytest.fixture
def manager(tmp_path):
    parent = SimpleNamespace(root_dir=str(tmp_path), virtual_home_root=str(tmp_path))
    limits = AttachmentLimits(
        max_upload_bytes=1024 * 1024,
        max_session_bytes=4 * 1024 * 1024,
        max_extracted_bytes=2 * 1024 * 1024,
        max_archive_entries=10,
        max_archive_ratio=100,
    )
    return SessionAttachmentManager(parent, limits=limits)


def make_zip(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in entries.items():
            archive.writestr(name, body)
    return output.getvalue()


def kernel_auth_handler(kernel_id: str, key: str, token: str):
    kernel = SimpleNamespace(session=SimpleNamespace(key=key.encode()))
    kernel_manager = SimpleNamespace(get_kernel=lambda requested: kernel if requested == kernel_id else None)
    return SimpleNamespace(
        request=SimpleNamespace(headers={"X-AUTH-BEAKER": token}),
        kernel_manager=kernel_manager,
    )


def test_kernel_authentication_returns_only_a_verified_kernel_id():
    provider = BeakerIdentityProvider()
    kernel_id = "kernel-one"
    nonce = "1234"
    key = "secret"
    digest = hashlib.sha256(f"{kernel_id}{nonce}{key}".encode()).hexdigest()
    token = f"beaker-kernel:{kernel_id}:{nonce}:{digest}"
    handler = kernel_auth_handler(kernel_id, key, token)

    assert provider.authenticated_beaker_kernel_id(handler) == kernel_id

    handler.request.headers["X-AUTH-BEAKER"] = f"beaker-kernel:{kernel_id}:{nonce}:forged"
    assert provider.authenticated_beaker_kernel_id(handler) is None


def test_attachment_handler_rejects_an_unverified_kernel_header():
    identity_provider = SimpleNamespace(
        beaker_kernel_header="X-AUTH-BEAKER",
        authenticated_beaker_kernel_id=MagicMock(return_value=None),
    )
    handler = SimpleNamespace(
        request=SimpleNamespace(headers={"X-AUTH-BEAKER": "beaker-kernel:victim:anything:forged"}),
        identity_provider=identity_provider,
    )

    with pytest.raises(web.HTTPError, match="Invalid kernel authentication") as error:
        SessionAttachmentHandler._authenticated_request_kernel_id(handler)

    assert error.value.status_code == 403


def test_kernel_clears_attachments_for_its_current_session():
    kernel = SimpleNamespace(
        beaker_session="session-one",
        session_id="fallback-session",
        jupyter_server="http://localhost:8890",
        api_auth=MagicMock(return_value="signed-token"),
    )
    response = SimpleNamespace(status_code=204, text="")

    with patch("beaker_notebook.kernel.requests.delete", return_value=response) as request:
        BeakerKernel.clear_session_attachments(kernel)

    request.assert_called_once_with(
        "http://localhost:8890/beaker/attachments/session-one",
        headers={"X-AUTH-BEAKER": "signed-token"},
        timeout=10,
    )


async def test_reset_kernel_clears_session_attachments_before_rebuilding_context():
    context = SimpleNamespace(
        SLUG="default",
        config={"context_info": {}},
        subkernel=SimpleNamespace(SLUG="python3"),
        session_attachments=[{"id": "old-attachment"}],
    )
    kernel = SimpleNamespace(
        context=context,
        clear_session_attachments=MagicMock(),
        set_context=AsyncMock(),
        send_set_chat_history=AsyncMock(),
    )
    message = SimpleNamespace(header={"msg_id": "reset-one"})

    with patch("beaker_notebook.kernel.reset_config"):
        await BeakerKernel.reset_kernel.__wrapped__(kernel, message)

    kernel.clear_session_attachments.assert_called_once_with()
    assert context.session_attachments == []
    kernel.set_context.assert_awaited_once_with(
        "default",
        context.config,
        subkernel="python3",
        parent_header=message.header,
    )


def test_regular_attachment_is_draft_until_committed(manager):
    attachment = manager.create_attachment(
        "session-one", "sales.csv", "text/csv", b"region,revenue\nwest,42\n"
    )

    assert attachment["committed"] is False
    assert attachment["files"] == ["sales.csv"]
    assert open(attachment["path"], "rb").read() == b"region,revenue\nwest,42\n"

    committed = manager.commit_attachments("session-one", [attachment["id"]])
    assert [item["id"] for item in committed] == [attachment["id"]]
    assert committed[0]["committed"] is True

    manager.delete_attachment("session-one", attachment["id"])
    assert manager.list_attachments("session-one") == []


def test_zip_is_extracted_and_original_is_retained(manager):
    attachment = manager.create_attachment(
        "session-one",
        "dataset.zip",
        "application/zip",
        make_zip({"data/customers.csv": b"id,name\n1,Ada\n", "README.txt": b"hello"}),
    )

    assert attachment["archive_status"] == "extracted"
    assert attachment["file_count"] == 2
    assert set(attachment["files"]) == {"data/customers.csv", "README.txt"}
    assert open(attachment["original_path"], "rb").read().startswith(b"PK")
    assert open(f"{attachment['root_path']}/data/customers.csv", "rb").read() == b"id,name\n1,Ada\n"


def test_unsafe_zip_keeps_original_and_reports_extraction_error(manager):
    attachment = manager.create_attachment(
        "session-one",
        "unsafe.zip",
        "application/zip",
        make_zip({"../escape.txt": b"nope"}),
    )

    assert attachment["archive_status"] == "failed"
    assert "unsafe path" in attachment["archive_error"]
    assert attachment["files"] == []
    assert open(attachment["original_path"], "rb").read().startswith(b"PK")


def test_upload_and_archive_limits_are_enforced(manager):
    with pytest.raises(AttachmentError, match="per-file limit"):
        manager.create_attachment(
            "session-one", "large.bin", "application/octet-stream", b"x" * (1024 * 1024 + 1)
        )

    limited = SessionAttachmentManager(
        manager.parent,
        limits=AttachmentLimits(
            max_upload_bytes=1024 * 1024,
            max_session_bytes=4 * 1024 * 1024,
            max_extracted_bytes=1024,
            max_archive_entries=1,
            max_archive_ratio=100,
        ),
    )
    attachment = limited.create_attachment(
        "session-two",
        "many.zip",
        "application/zip",
        make_zip({"one.txt": b"one", "two.txt": b"two"}),
    )
    assert attachment["archive_status"] == "failed"
    assert "limit is 1" in attachment["archive_error"]


def test_session_cleanup_removes_every_attachment(manager):
    manager.create_attachment("session-one", "one.txt", "text/plain", b"one")
    manager.create_attachment("session-one", "two.txt", "text/plain", b"two")
    assert len(manager.list_attachments("session-one")) == 2

    manager.delete_session("session-one")
    assert manager.list_attachments("session-one") == []


def test_runtime_cleanup_removes_attachments_from_all_sessions(manager):
    manager.create_attachment("session-one", "one.txt", "text/plain", b"one")
    manager.create_attachment("session-two", "two.txt", "text/plain", b"two")

    manager.cleanup()

    assert manager.list_attachments("session-one") == []
    assert manager.list_attachments("session-two") == []


def _limits() -> AttachmentLimits:
    return AttachmentLimits(
        max_upload_bytes=1024 * 1024,
        max_session_bytes=4 * 1024 * 1024,
        max_extracted_bytes=2 * 1024 * 1024,
        max_archive_entries=10,
        max_archive_ratio=100,
    )


def test_local_mode_stores_under_shared_data_dir_ignoring_working_dir(tmp_path, monkeypatch):
    from beaker_notebook.services.auth import BeakerUser

    data_dir = tmp_path / "beaker-data"
    working_dir = tmp_path / "cwd"
    monkeypatch.setattr(
        "beaker_notebook.services.attachments.BEAKER_LOCAL_DATA_PATH", data_dir
    )
    parent = SimpleNamespace(
        root_dir=str(working_dir),
        virtual_home_root=str(working_dir),
        local_mode=True,
    )
    manager = SessionAttachmentManager(parent, limits=_limits())

    # Even a request carrying a BeakerUser must not scatter files into a home/working dir.
    user = BeakerUser(username="alice")
    attachment = manager.create_attachment("session-one", "one.txt", "text/plain", b"one", user)

    stored = Path(attachment["path"])
    assert data_dir.resolve() / "session-attachments" in stored.resolve().parents
    assert working_dir not in stored.resolve().parents


def test_server_mode_namespaces_attachments_under_the_user_home(tmp_path):
    from beaker_notebook.services.auth import BeakerUser

    home_root = tmp_path / "homes"
    parent = SimpleNamespace(
        root_dir=str(tmp_path / "cwd"),
        virtual_home_root=str(home_root),
        local_mode=False,
    )
    manager = SessionAttachmentManager(parent, limits=_limits())

    user = BeakerUser(username="alice")
    attachment = manager.create_attachment("session-one", "one.txt", "text/plain", b"one", user)

    stored = Path(attachment["path"]).resolve()
    expected_base = (home_root / user.home_dir / ".beaker" / "session-attachments").resolve()
    assert expected_base in stored.parents


def test_local_mode_cleanup_preserves_the_shared_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "beaker-data"
    # A sibling artifact the local data dir is expected to also hold.
    (data_dir / "notebooks").mkdir(parents=True)
    monkeypatch.setattr(
        "beaker_notebook.services.attachments.BEAKER_LOCAL_DATA_PATH", data_dir
    )
    parent = SimpleNamespace(
        root_dir=str(tmp_path / "cwd"),
        virtual_home_root=str(tmp_path / "cwd"),
        local_mode=True,
    )
    manager = SessionAttachmentManager(parent, limits=_limits())
    manager.create_attachment("session-one", "one.txt", "text/plain", b"one")

    manager.cleanup()

    assert manager.list_attachments("session-one") == []
    assert data_dir.is_dir()
    assert (data_dir / "notebooks").is_dir()

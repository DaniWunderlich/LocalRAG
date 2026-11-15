"""Damaged chat records must not disable navigation or cause private data loss."""

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from rag.errors import AppError
from tests.conftest import Harness
from tests.test_conversations import attach, create


@pytest.mark.parametrize("damage", ["json", "id", "filename"])
def test_bad_chat_does_not_break_listing_or_recovery(
    harness: Harness, caplog: pytest.LogCaptureFixture, damage: str
) -> None:
    healthy, damaged = create(harness), create(harness)
    path = harness.services.chats.path / f"{damaged}.json"
    if damage == "json":
        path.write_bytes(b'{"private-sentinel":')
    elif damage == "id":
        data = json.loads(path.read_bytes())
        data["conversation_id"] = str(uuid4())
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        invalid = path.with_name("not-a-uuid.json")
        invalid.write_bytes(path.read_bytes())
        path.unlink()
        path = invalid
    original = path.read_bytes()
    response = harness.client.get("/api/v1/conversations")
    assert response.status_code == 200
    assert [item["conversation_id"] for item in response.json()] == [healthy]
    assert any(getattr(record, "record_name", None) == path.name for record in caplog.records)
    assert "private-sentinel" not in caplog.text
    with pytest.raises(AppError) as error:
        harness.services.chats.all()
    assert error.value.code == "chat_record_unreadable"
    if damage != "filename":
        response = harness.client.get(f"/api/v1/conversations/{damaged}")
        assert response.status_code == 409
        assert response.json()["code"] == "chat_record_unreadable"
    harness.client.portal.call(harness.services.recover)  # type: ignore[union-attr]
    assert path.read_bytes() == original
    assert harness.client.get(f"/api/v1/conversations/{healthy}").status_code == 200


@pytest.mark.parametrize("action", ["delete_chat", "detach"])
def test_unknown_chat_references_block_private_file_cleanup(harness: Harness, action: str) -> None:
    first, second = create(harness), create(harness)
    document = attach(harness, first)
    attach(harness, second)
    path = harness.services.chats.path / f"{second}.json"
    path.write_bytes(b"{broken")
    document_id = UUID(str(document["document_id"]))
    endpoint = f"/api/v1/conversations/{first}"
    if action == "detach":
        endpoint += f"/documents/{document_id}"
    response = harness.client.delete(endpoint)
    assert response.status_code == 409
    assert response.json()["code"] == "chat_record_unreadable"
    chat = harness.client.get(f"/api/v1/conversations/{first}").json()
    assert chat["status"] == "active"
    assert chat["document_ids"] == [str(document_id)]
    assert harness.services.registry.file_path(document_id).is_file()
    meta = harness.services.registry.get(document_id)
    assert meta is not None and meta.status == "indexed"
    assert path.read_bytes() == b"{broken"


def test_pending_deletion_recovers_after_a_damaged_chat_is_restored(harness: Harness) -> None:
    first, second = create(harness), create(harness)
    document = attach(harness, first)
    attach(harness, second)
    path = harness.services.chats.path / f"{second}.json"
    original = path.read_bytes()
    path.write_bytes(b"{broken")
    pending = harness.services.chats.get(UUID(first))
    assert pending is not None
    harness.services.chats.save(pending.model_copy(update={"status": "deleting"}))
    harness.client.portal.call(harness.services.recover)  # type: ignore[union-attr]
    assert harness.services.registry.file_path(UUID(str(document["document_id"]))).exists()
    assert harness.client.get(f"/api/v1/conversations/{first}").json()["status"] == "deleting"
    path.write_bytes(original)
    harness.client.portal.call(harness.services.recover)  # type: ignore[union-attr]
    assert harness.client.get(f"/api/v1/conversations/{first}").status_code == 404
    assert harness.services.registry.file_path(UUID(str(document["document_id"]))).exists()


def test_shared_library_files_do_not_need_orphan_cleanup(harness: Harness) -> None:
    first, damaged = create(harness), create(harness)
    document = attach(harness, first)
    assert (
        harness.client.post(
            "/api/v1/documents",
            files={"file": ("library.txt", b"The release is on Friday.", "text/plain")},
        ).status_code
        == 201
    )
    (harness.services.chats.path / f"{damaged}.json").write_bytes(b"{broken")
    assert harness.client.delete(f"/api/v1/conversations/{first}").status_code == 204
    assert harness.services.registry.file_path(UUID(str(document["document_id"]))).exists()


def test_unreadable_file_is_reported_without_exposing_exception_content(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    healthy, damaged = create(harness), create(harness)
    path = harness.services.chats.path / f"{damaged}.json"
    original = Path.read_bytes

    def read_bytes(target: Path) -> bytes:
        if target == path:
            raise PermissionError("private-sentinel")
        return original(target)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    response = harness.client.get("/api/v1/conversations")
    assert response.status_code == 200
    assert [item["conversation_id"] for item in response.json()] == [healthy]
    response = harness.client.get(f"/api/v1/conversations/{damaged}")
    assert response.status_code == 409
    assert "private-sentinel" not in response.text + caplog.text


def test_python314_cleanup_also_catches_oserror(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    key = create(harness)
    document = attach(harness, key)
    document_id = UUID(str(document["document_id"]))
    meta = harness.services.registry.get(document_id)
    assert meta is not None
    harness.services.registry.save(meta.model_copy(update={"status": "deleting"}))
    target = harness.services.registry.file_path(document_id)
    original = Path.unlink

    def unlink(path: Path, missing_ok: bool = False) -> None:
        if path == target:
            raise OSError("simulated filesystem failure")
        original(path, missing_ok=missing_ok)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", unlink)
        harness.client.portal.call(harness.services.recover)  # type: ignore[union-attr]
    assert target.exists()
    assert "document_cleanup_pending" in caplog.text
    harness.client.portal.call(harness.services.recover)  # type: ignore[union-attr]
    assert not target.exists()

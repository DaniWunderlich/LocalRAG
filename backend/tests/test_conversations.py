"""Persistent threads, evidence isolation, retry semantics and private file lifecycle."""

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from rag.errors import AppError
from rag.storage.conversations import ConversationStore
from tests.conftest import Harness


def create(harness: Harness, **fields: object) -> str:
    """Create a local thread with a test completion model."""
    response = harness.client.post("/api/v1/conversations", json={"model": "chat:test", **fields})
    assert response.status_code == 201, response.text
    return response.json()["conversation_id"]


def attach(
    harness: Harness, chat_id: str, text: bytes = b"The release is on Friday."
) -> dict[str, object]:
    """Upload a private document to an explicitly selected thread."""
    response = harness.client.post(
        f"/api/v1/conversations/{chat_id}/documents",
        files={"file": ("plan.txt", text, "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def send(
    harness: Harness, chat_id: str, question: str = "When is the release?"
) -> dict[str, object]:
    """Require a complete, durable exchange."""
    response = harness.client.post(
        f"/api/v1/conversations/{chat_id}/messages",
        json={"message": question, "request_id": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_private_documents_do_not_leak_into_other_chats_or_library(harness: Harness) -> None:
    first, second = create(harness), create(harness)
    document = attach(harness, first)
    assert document["in_library"] is False
    assert harness.client.get("/api/v1/documents").json() == []
    assert harness.client.post("/api/v1/search", json={"query": "Friday"}).json() == []
    answered = send(harness, first)
    assert answered["messages"][-1]["sources"][0]["document_id"] == document["document_id"]
    other = send(harness, second)
    assert other["messages"][-1]["sources"] == []
    assert "enough context" in other["messages"][-1]["content"]


def test_library_is_explicitly_opted_in_per_thread(harness: Harness) -> None:
    response = harness.client.post(
        "/api/v1/documents",
        files={"file": ("shared.txt", b"Friday release", "text/plain")},
    )
    assert response.status_code == 201
    chat_id = create(harness)
    assert send(harness, chat_id)["messages"][-1]["sources"] == []
    harness.client.patch(f"/api/v1/conversations/{chat_id}", json={"use_library": True})
    assert send(harness, chat_id)["messages"][-1]["sources"]


def test_shared_hash_is_reused_without_double_indexing(harness: Harness) -> None:
    first, second = create(harness), create(harness)
    original = attach(harness, first)
    duplicate = attach(harness, second)
    assert duplicate["document_id"] == original["document_id"]
    assert len(harness.services.registry.list()) == 1
    assert harness.client.delete(f"/api/v1/conversations/{first}").status_code == 204
    assert harness.services.registry.get(UUID(str(original["document_id"]))) is not None
    assert send(harness, second)["messages"][-1]["sources"]
    assert harness.client.delete(f"/api/v1/conversations/{second}").status_code == 204
    assert harness.services.registry.list() == []


def test_promoting_an_attachment_to_library_preserves_it_after_chat_deletion(
    harness: Harness,
) -> None:
    chat_id = create(harness)
    original = attach(harness, chat_id)
    promoted = harness.client.post(
        "/api/v1/documents",
        files={"file": ("shared.txt", b"The release is on Friday.", "text/plain")},
    )
    assert promoted.status_code == 201
    assert promoted.json()["document_id"] == original["document_id"]
    assert promoted.json()["in_library"] is True
    assert harness.client.delete(f"/api/v1/conversations/{chat_id}").status_code == 204
    assert len(harness.client.get("/api/v1/documents").json()) == 1


def test_follow_up_uses_only_this_conversations_history(harness: Harness) -> None:
    first, second = create(harness), create(harness)
    attach(harness, first)
    attach(harness, second, b"Monday is the workshop date.")
    send(harness, first, "When is the Friday release?")
    send(harness, second, "What about the workshop?")
    send(harness, first, "Who manages it?")
    calls = [body for path, body in harness.ollama.requests if path == "/api/chat"]
    prompt = calls[-1]["messages"]
    assert [item["role"] for item in prompt] == ["system", "user", "assistant", "user"]
    assert prompt[1]["content"] == "When is the Friday release?"
    assert "workshop" not in str(prompt)
    assert "[Source 1]" not in prompt[2]["content"]


def test_retried_request_does_not_duplicate_saved_messages(harness: Harness) -> None:
    chat_id = create(harness)
    attach(harness, chat_id)
    body = {"message": "When?", "request_id": str(uuid4())}
    first = harness.client.post(f"/api/v1/conversations/{chat_id}/messages", json=body)
    second = harness.client.post(f"/api/v1/conversations/{chat_id}/messages", json=body)
    assert first.json() == second.json()
    assert len(second.json()["messages"]) == 2
    assert len([path for path, _ in harness.ollama.requests if path == "/api/chat"]) == 1
    body["message"] = "Another question"
    assert (
        harness.client.post(f"/api/v1/conversations/{chat_id}/messages", json=body).status_code
        == 409
    )


def test_rename_settings_and_transcript_survive_store_reload(harness: Harness) -> None:
    chat_id = create(harness, top_k=3, temperature=0)
    response = harness.client.patch(
        f"/api/v1/conversations/{chat_id}",
        json={"title": "Release planning", "use_library": True},
    )
    assert response.status_code == 200
    attach(harness, chat_id)
    send(harness, chat_id)
    restored = ConversationStore(harness.services.registry.path).get(UUID(chat_id))
    assert restored is not None
    assert restored.title == "Release planning"
    assert restored.top_k == 3
    assert restored.temperature == 0
    assert restored.use_library is True
    assert len(restored.messages) == 2


def test_failed_generation_does_not_commit_half_an_exchange(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = create(harness)
    attach(harness, chat_id)
    monkeypatch.setattr(
        harness.services.ollama, "chat", AsyncMock(side_effect=AppError("Unavailable."))
    )
    response = harness.client.post(
        f"/api/v1/conversations/{chat_id}/messages",
        json={"message": "When?", "request_id": str(uuid4())},
    )
    assert response.status_code == 503
    assert harness.client.get(f"/api/v1/conversations/{chat_id}").json()["messages"] == []


def test_interrupted_chat_deletion_can_be_recovered(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = create(harness)
    attach(harness, chat_id)
    original = harness.services.qdrant.delete_document
    monkeypatch.setattr(
        harness.services.qdrant, "delete_document", AsyncMock(side_effect=AppError("Unavailable."))
    )
    assert harness.client.delete(f"/api/v1/conversations/{chat_id}").status_code == 503
    assert harness.client.get(f"/api/v1/conversations/{chat_id}").json()["status"] == "deleting"
    monkeypatch.setattr(harness.services.qdrant, "delete_document", original)
    harness.client.portal.call(harness.services.recover)  # type: ignore[union-attr]
    assert harness.client.get(f"/api/v1/conversations/{chat_id}").status_code == 404
    assert harness.services.registry.list() == []


def test_detaching_private_file_removes_original_and_vectors(harness: Harness) -> None:
    chat_id = create(harness)
    document = attach(harness, chat_id)
    document_id = str(document["document_id"])
    response = harness.client.delete(f"/api/v1/conversations/{chat_id}/documents/{document_id}")
    assert response.status_code == 204
    assert harness.client.get(f"/api/v1/conversations/{chat_id}").json()["document_ids"] == []
    assert not harness.services.registry.file_path(UUID(document_id)).exists()


def test_failed_attachment_is_visible_and_can_be_retried(harness: Harness) -> None:
    chat_id = create(harness)
    harness.ollama.fail_embeddings = True
    response = harness.client.post(
        f"/api/v1/conversations/{chat_id}/documents",
        files={"file": ("retry.txt", b"Friday release", "text/plain")},
    )
    assert response.status_code == 503
    failed = harness.client.get(f"/api/v1/conversations/{chat_id}/documents").json()[0]
    assert failed["status"] == "failed"
    assert harness.client.get("/api/v1/documents").json() == []
    harness.ollama.fail_embeddings = False
    retried = attach(harness, chat_id, b"Friday release")
    assert retried["document_id"] == failed["document_id"]


@pytest.mark.parametrize(
    "body", [{"title": ""}, {"top_k": 21}, {"temperature": -1}, {"use_library": "invalid"}]
)
def test_invalid_chat_edits_are_rejected(harness: Harness, body: dict[str, object]) -> None:
    chat_id = create(harness)
    assert harness.client.patch(f"/api/v1/conversations/{chat_id}", json=body).status_code == 422


def test_session_transcript_import_is_durable_and_idempotent(harness: Harness) -> None:
    conversation_id = str(uuid4())
    body = {
        "conversation_id": conversation_id,
        "model": "chat:test",
        "top_k": 3,
        "temperature": 0,
        "messages": [
            {"role": "user", "content": "When is the release?"},
            {"role": "assistant", "content": "Friday.", "sources": []},
        ],
    }
    first = harness.client.post("/api/v1/conversations/import", json=body)
    assert first.status_code == 201, first.text
    second = harness.client.post("/api/v1/conversations/import", json=body)
    assert first.json() == second.json()
    restored = ConversationStore(harness.services.registry.path).get(UUID(conversation_id))
    assert restored is not None and len(restored.messages) == 2
    assert restored.use_library is True
    assert restored.temperature == 0
    assert not any(path == "/api/chat" for path, _ in harness.ollama.requests)


def test_deleting_an_original_prunes_links_but_keeps_historical_sources(
    harness: Harness,
) -> None:
    chat_id = create(harness)
    document = attach(harness, chat_id)
    send(harness, chat_id)
    document_id = str(document["document_id"])
    assert harness.client.delete(f"/api/v1/documents/{document_id}").status_code == 204
    restored = harness.client.get(f"/api/v1/conversations/{chat_id}").json()
    assert restored["document_ids"] == []
    assert restored["messages"][-1]["sources"][0]["document_id"] == document_id


def test_recovery_prunes_an_attachment_removed_during_interrupted_detach(harness: Harness) -> None:
    chat_id = create(harness)
    document = attach(harness, chat_id)
    document_id = UUID(str(document["document_id"]))
    meta = harness.services.registry.get(document_id)
    assert meta is not None
    harness.services.registry.save(meta.model_copy(update={"status": "deleting"}))
    harness.client.portal.call(harness.services.recover)  # type: ignore[union-attr]
    assert harness.client.get(f"/api/v1/conversations/{chat_id}").json()["document_ids"] == []

"""General answers without documents and strict boundaries for document answers."""

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from rag.errors import AppError
from rag.generation.generator import NO_CONTEXT
from rag.storage.conversations import ConversationStore
from tests.conftest import Harness
from tests.test_conversations import attach, create, send


@pytest.mark.parametrize("use_library", [False, True])
def test_general_chat_is_durable_and_idempotent_without_embedding_calls(
    harness: Harness, use_library: bool
) -> None:
    key = create(harness, temperature=0)
    harness.client.patch(f"/api/v1/conversations/{key}", json={"use_library": use_library})
    harness.ollama.fail_embeddings = True
    body = {"message": "Was ist eine Primzahl?", "request_id": str(uuid4())}
    endpoint = f"/api/v1/conversations/{key}/messages"
    first = harness.client.post(endpoint, json=body)
    assert first.status_code == 200, first.text
    second = harness.client.post(endpoint, json=body)
    assert first.json() == second.json()
    answer = first.json()["messages"][-1]
    assert answer["content"] == harness.ollama.general_answer
    assert answer["sources"] == []
    calls = [body for path, body in harness.ollama.requests if path == "/api/chat"]
    assert len(calls) == 1
    assert calls[0]["messages"][-1]["content"] == "Was ist eine Primzahl?"
    assert calls[0]["options"]["temperature"] == 0
    assert not any(path == "/api/embed" for path, _ in harness.ollama.requests)
    restored = ConversationStore(harness.services.registry.path).get(UUID(key))
    assert restored is not None and len(restored.messages) == 2
    assert restored.messages[-1].content == harness.ollama.general_answer


def test_general_follow_up_uses_only_the_current_chats_history(harness: Harness) -> None:
    first, other = create(harness), create(harness)
    send(harness, first, "Explain prime numbers.")
    send(harness, other, "Unrelated private workshop question.")
    send(harness, first, "Give me an example.")
    calls = [body for path, body in harness.ollama.requests if path == "/api/chat"]
    prompt = calls[-1]["messages"]
    assert [turn["role"] for turn in prompt] == ["system", "user", "assistant", "user"]
    assert prompt[1]["content"] == "Explain prime numbers."
    assert prompt[-1]["content"] == "Give me an example."
    assert "general knowledge" in prompt[0]["content"]
    assert "workshop" not in str(prompt)


def test_adding_and_removing_the_last_document_switches_generation_mode(harness: Harness) -> None:
    key = create(harness)
    assert send(harness, key)["messages"][-1]["sources"] == []
    document = attach(harness, key)
    grounded = send(harness, key)
    assert grounded["messages"][-1]["sources"][0]["document_id"] == document["document_id"]
    assert "[Source 1]" in grounded["messages"][-1]["content"]
    assert (
        harness.client.delete(
            f"/api/v1/conversations/{key}/documents/{document['document_id']}"
        ).status_code
        == 204
    )
    general = send(harness, key, "Now explain prime numbers.")
    assert general["messages"][-1]["sources"] == []
    assert general["messages"][-1]["content"] == harness.ollama.general_answer
    calls = [body for path, body in harness.ollama.requests if path == "/api/chat"]
    assert "supplied document excerpts" in calls[-2]["messages"][0]["content"]
    assert "general knowledge" in calls[-1]["messages"][0]["content"]
    assert "[Source 1]" not in str(calls[-1]["messages"])


@pytest.mark.parametrize("saved_chat", [True, False])
def test_selected_documents_without_hits_do_not_fall_back_to_general_knowledge(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, saved_chat: bool
) -> None:
    key = create(harness)
    if saved_chat:
        attach(harness, key)
    else:
        assert (
            harness.client.post(
                "/api/v1/documents", files={"file": ("plan.txt", b"Friday release", "text/plain")}
            ).status_code
            == 201
        )
    harness.ollama.requests.clear()
    monkeypatch.setattr(harness.services.qdrant, "search", AsyncMock(return_value=[]))
    if saved_chat:
        answer = send(harness, key)["messages"][-1]
        assert answer["content"] == NO_CONTEXT
    else:
        response = harness.client.post("/api/v1/chat", json={"message": "An unsupported question"})
        assert response.status_code == 200
        answer = response.json()
        assert answer["answer"] == NO_CONTEXT
    assert answer["sources"] == []
    assert not any(path == "/api/chat" for path, _ in harness.ollama.requests)


def test_general_generation_failure_keeps_retry_atomic(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = create(harness)
    original = harness.services.ollama.chat
    monkeypatch.setattr(
        harness.services.ollama, "chat", AsyncMock(side_effect=AppError("Unavailable."))
    )
    body = {"message": "Explain prime numbers.", "request_id": str(uuid4())}
    endpoint = f"/api/v1/conversations/{key}/messages"
    assert harness.client.post(endpoint, json=body).status_code == 503
    assert harness.client.get(f"/api/v1/conversations/{key}").json()["messages"] == []
    monkeypatch.setattr(harness.services.ollama, "chat", original)
    response = harness.client.post(endpoint, json=body)
    assert response.status_code == 200 and len(response.json()["messages"]) == 2
    assert harness.client.post(endpoint, json=body).json() == response.json()
    assert len([path for path, _ in harness.ollama.requests if path == "/api/chat"]) == 1


def test_general_chat_rejects_invented_document_citations(harness: Harness) -> None:
    key = create(harness)
    harness.ollama.general_answer = "An unsupported claim [Source 1]"
    response = harness.client.post(
        f"/api/v1/conversations/{key}/messages",
        json={"message": "Explain prime numbers.", "request_id": str(uuid4())},
    )
    assert response.status_code == 502 and response.json()["code"] == "invalid_citation"
    assert harness.client.get(f"/api/v1/conversations/{key}").json()["messages"] == []


def test_general_chat_bounds_old_history(harness: Harness) -> None:
    key = create(harness)
    send(harness, key, "x" * 4000)
    send(harness, key, "A short follow-up.")
    calls = [body for path, body in harness.ollama.requests if path == "/api/chat"]
    prompt = calls[-1]["messages"]
    assert [turn["role"] for turn in prompt] == ["system", "user"]
    assert prompt[-1]["content"] == "A short follow-up."


def test_stateless_general_chat_cannot_read_another_chats_private_attachment(
    harness: Harness,
) -> None:
    key = create(harness)
    attach(harness, key, b"Private sentinel: the secret code is CHERRY-712.")
    harness.ollama.requests.clear()
    response = harness.client.post("/api/v1/chat", json={"message": "Say hello."})
    assert response.status_code == 200
    assert response.json()["answer"] == harness.ollama.general_answer
    assert response.json()["sources"] == []
    prompt = [body for path, body in harness.ollama.requests if path == "/api/chat"][-1]["messages"]
    assert "CHERRY-712" not in str(prompt)
    assert not any(path == "/api/embed" for path, _ in harness.ollama.requests)

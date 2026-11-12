"""Gradio workspace tests for persistent conversations and inline documents."""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api_client import BackendClient, BackendError
from workspace import Draft, Session, Workspace, source_details, transcript

ROOT = Path(__file__).parents[1]


class BackendDouble:
    """An inspectable transport double; no frontend callback performs RAG work."""

    def __init__(self) -> None:
        self.chats: dict[str, dict[str, Any]] = {}
        self.documents: dict[str, list[dict[str, Any]]] = {}
        self.uploads: list[tuple[str, str, bytes]] = []
        self.submissions: list[tuple[str, str, str]] = []
        self.fail_send = False

    def summaries(self) -> list[dict[str, Any]]:
        return [
            {
                "conversation_id": key,
                "title": value["title"],
                "folder": value.get("folder", ""),
                "message_count": len(value["messages"]),
                "document_count": len(value["document_ids"]),
                "status": "active",
            }
            for key, value in self.chats.items()
        ]

    def create(self, model: str, top_k: int, temperature: float) -> dict[str, Any]:
        key = str(uuid4())
        chat = {
            "conversation_id": key,
            "title": "New chat",
            "folder": "",
            "model": model,
            "top_k": top_k,
            "temperature": temperature,
            "use_library": False,
            "messages": [],
            "document_ids": [],
            "status": "active",
        }
        self.chats[key] = chat
        self.documents[key] = []
        return deepcopy(chat)

    def update(self, conversation_id: str, **fields: Any) -> dict[str, Any]:
        self.chats[conversation_id].update(fields)
        return deepcopy(self.chats[conversation_id])

    def upload(
        self, conversation_id: str, name: str, data: bytes, content_type: str
    ) -> dict[str, Any]:
        self.uploads.append((conversation_id, name, data))
        chat = self.chats[conversation_id]
        document = {
            "document_id": str(uuid4()),
            "filename": name,
            "size_bytes": len(data),
            "chunk_count": 1,
            "status": "indexed",
            "error": None,
        }
        chat["document_ids"].append(document["document_id"])
        self.documents[conversation_id].append(document)
        return document

    def send(self, conversation_id: str, message: str, request_id: str) -> dict[str, Any]:
        self.submissions.append((conversation_id, message, request_id))
        if self.fail_send:
            raise BackendError("Ollama is temporarily unavailable.")
        chat = self.chats[conversation_id]
        chat["title"] = message[:70]
        chat["messages"].extend(
            [
                {"message_id": request_id, "role": "user", "content": message, "sources": []},
                {
                    "message_id": str(uuid4()),
                    "role": "assistant",
                    "content": "The release is on Friday. [Source 1]",
                    "sources": [
                        {
                            "source_id": 1,
                            "filename": "release.txt",
                            "page": 2,
                            "section": None,
                            "score": 0.9,
                            "chunk_id": "test-chunk",
                            "chunk_index": 0,
                            "text": "The release is on Friday.",
                        }
                    ],
                },
            ]
        )
        return deepcopy(chat)


@contextmanager
def fake_backend() -> Iterator[BackendDouble]:
    """Patch only the HTTP boundary while retaining the real page interactions."""
    backend = BackendDouble()
    methods = {
        "models": lambda: {
            "models": ["chat:test"],
            "default_model": "chat:test",
            "defaults": {"top_k": 7, "temperature": 0.3, "max_upload_bytes": 20971520},
        },
        "conversations": backend.summaries,
        "conversation": lambda key: deepcopy(backend.chats[key]),
        "create_conversation": backend.create,
        "update_conversation": backend.update,
        "delete_conversation": lambda key: (backend.chats.pop(key), backend.documents.pop(key)),
        "attachments": lambda key: deepcopy(backend.documents[key]),
        "upload_attachment": backend.upload,
        "send_message": backend.send,
        "documents": lambda: [],
        "request": lambda *args, **kwargs: {"status": "ready"},
    }
    with ExitStack() as stack:
        for name, implementation in methods.items():
            stack.enter_context(patch.object(BackendClient, name, side_effect=implementation))
        yield backend


def make_workspace(tmp_path: Path) -> tuple[Workspace, Session]:
    """Use a bounded temporary upload root and initialise the patched HTTP boundary."""
    controller = Workspace(upload_root=tmp_path)
    session = Session()
    controller.initialise(session)
    return controller, session


def test_native_app_serves_health_and_gradio_components() -> None:
    from app import app

    with TestClient(app) as client:
        assert client.get("/health/live").json() == {"status": "alive"}
        config = client.get("/config").json()
        kinds = {item["type"] for item in config["components"]}
        assert {"chatbot", "multimodaltextbox", "sidebar", "state", "dataframe"} <= kinds
        assert config["analytics_enabled"] is False
        assert config["enable_queue"] is True


def test_text_and_file_share_a_single_durable_conversation(tmp_path: Path) -> None:
    with fake_backend() as backend:
        controller, session = make_workspace(tmp_path)
        file = tmp_path / "release.txt"
        file.write_text("Friday release")
        controller.submit(session, {"text": "When is the release?", "files": [str(file)]})
        assert len(backend.chats) == 1
        assert len(backend.uploads) == len(backend.submissions) == 1
        assert backend.uploads[0][0] == backend.submissions[0][0] == session.active_id
        assert session.pending == {}
        assert session.drafts == {}
        assert "Sources (1)" in transcript(session)[-1]["content"]


def test_files_alone_do_not_generate_an_answer(tmp_path: Path) -> None:
    with fake_backend() as backend:
        controller, session = make_workspace(tmp_path)
        file = tmp_path / "release.md"
        file.write_text("Friday")
        controller.submit(session, {"text": "", "files": [str(file)]})
        assert len(backend.chats) == len(backend.uploads) == 1
        assert backend.submissions == []


def test_chat_switching_retains_distinct_unsent_drafts(tmp_path: Path) -> None:
    with fake_backend() as backend:
        first = backend.create("chat:test", 5, 0.2)["conversation_id"]
        second = backend.create("chat:test", 5, 0.2)["conversation_id"]
        controller, session = make_workspace(tmp_path)
        controller.select(session, first, None)
        controller.select(session, second, {"text": "First unsent question", "files": []})
        controller.select(session, first, {"text": "Second unsent question", "files": []})
        assert session.drafts[first].text == "First unsent question"
        assert session.drafts[second].text == "Second unsent question"
        assert session.conversation is not None and session.conversation["messages"] == []


def test_library_icon_updates_only_the_selected_chat(tmp_path: Path) -> None:
    with fake_backend() as backend:
        first = backend.create("chat:test", 5, 0.2)["conversation_id"]
        second = backend.create("chat:test", 5, 0.2)["conversation_id"]
        controller, session = make_workspace(tmp_path)
        controller.select(session, first, None)
        controller.toggle_library(session)
        assert session.use_library is True
        assert backend.chats[first]["use_library"] is True
        assert backend.chats[second]["use_library"] is False
        controller.toggle_library(session)
        assert session.use_library is False


def test_unsaved_library_choice_applies_to_the_created_chat(tmp_path: Path) -> None:
    with fake_backend() as backend:
        controller, session = make_workspace(tmp_path)
        controller.toggle_library(session)
        controller.submit(session, {"text": "Use the library", "files": []})
        assert next(iter(backend.chats.values()))["use_library"] is True
        assert session.new_use_library is False


def test_retry_keeps_request_id_and_skips_successful_uploads(tmp_path: Path) -> None:
    with fake_backend() as backend:
        controller, session = make_workspace(tmp_path)
        file = tmp_path / "release.txt"
        file.write_text("Friday")
        backend.fail_send = True
        with pytest.raises(BackendError):
            controller.submit(session, {"text": "When?", "files": [str(file)]})
        assert len(backend.uploads) == 1
        key = session.key
        request_id = session.pending[key].request_id
        assert session.pending[key].draft.files == []
        backend.fail_send = False
        controller.retry(session)
        assert backend.submissions[-1][2] == request_id
        assert len(backend.uploads) == 1
        assert len(backend.chats[key]["messages"]) == 2


def test_failed_submissions_stay_with_the_original_chat(tmp_path: Path) -> None:
    with fake_backend() as backend:
        controller, session = make_workspace(tmp_path)
        backend.fail_send = True
        with pytest.raises(BackendError):
            controller.submit(session, {"text": "First question", "files": []})
        first = session.key
        controller.new(session, None)
        backend.fail_send = False
        controller.submit(session, {"text": "Second question", "files": []})
        assert first in session.pending
        assert session.key not in session.pending
        controller.discard(session)
        assert first in session.pending
        controller.select(session, first, None)
        assert session.pending[first].draft.text == "First question"


def test_settings_are_saved_on_the_chat_without_changing_defaults(tmp_path: Path) -> None:
    with fake_backend() as backend:
        controller, session = make_workspace(tmp_path)
        controller.new(session, None)
        controller.save_settings(session, "Release plan", "chat:alternative", 3, 0.1)
        assert backend.chats[session.key]["title"] == "Release plan"
        assert backend.chats[session.key]["model"] == "chat:alternative"
        assert backend.chats[session.key]["top_k"] == 3
        assert session.model == "chat:test"
        assert session.top_k == 7


def test_invalid_uploads_do_not_create_chats(tmp_path: Path) -> None:
    with fake_backend() as backend:
        controller, session = make_workspace(tmp_path)
        file = tmp_path / "unsafe.exe"
        file.write_text("test")
        with pytest.raises(BackendError, match="Use PDF"):
            controller.submit(session, {"files": [str(file)]})
        with pytest.raises(BackendError, match="temporary upload"):
            controller.submit(session, {"files": [str(tmp_path / "missing.txt")]})
        assert backend.chats == {}


def test_file_paths_outside_the_upload_root_are_rejected(tmp_path: Path) -> None:
    with fake_backend():
        controller, session = make_workspace(tmp_path / "uploads")
        file = tmp_path / "private.txt"
        file.write_text("Private server file")
        with pytest.raises(BackendError, match="temporary upload"):
            controller.validate(session, Draft(files=[str(file)]))


def test_oversized_upload_and_question_are_rejected_before_indexing(tmp_path: Path) -> None:
    with fake_backend() as backend:
        controller, session = make_workspace(tmp_path)
        session.max_upload_bytes = 3
        file = tmp_path / "large.txt"
        file.write_text("Friday")
        with pytest.raises(BackendError, match="upload limit"):
            controller.submit(session, {"files": [str(file)]})
        with pytest.raises(BackendError, match="8,000"):
            controller.submit(session, {"text": "x" * 8001})
        assert backend.uploads == []
        assert backend.chats == {}


def test_saved_chat_restores_when_models_are_unavailable(tmp_path: Path) -> None:
    with fake_backend() as backend:
        key = backend.create("chat:test", 5, 0.2)["conversation_id"]
        with patch.object(BackendClient, "models", side_effect=BackendError("Ollama unavailable.")):
            controller = Workspace(upload_root=tmp_path)
            session = Session()
            controller.initialise(session, key)
        assert session.active_id == key
        assert session.conversation == backend.chats[key]
        assert session.service_notice == "Ollama unavailable."


def test_source_snapshots_are_escaped_and_can_hide_excerpt_text() -> None:
    sources = [
        {
            "source_id": 1,
            "filename": "<script>bad</script>.txt",
            "page": 2,
            "section": None,
            "chunk_index": 0,
            "score": 0.9,
            "text": "<img src=x onerror=alert(1)>",
        }
    ]
    result = source_details(sources, True)
    assert "<script>" not in result
    assert "<img" not in result
    assert "&lt;script&gt;" in result
    assert "similarity 0.900" in result
    assert "<pre>" not in source_details(sources, False)
    assert "Sources (1)" in source_details(sources, False)


def test_destructive_actions_require_confirmation(tmp_path: Path) -> None:
    with fake_backend():
        controller, session = make_workspace(tmp_path)
        controller.new(session, None)
        with patch.object(BackendClient, "delete_conversation") as deleted:
            with pytest.raises(BackendError, match="Confirm"):
                controller.delete_chat(session, False)
            deleted.assert_not_called()
        with patch.object(BackendClient, "delete") as removed:
            with pytest.raises(BackendError, match="Select"):
                controller.delete_document(session, False)
            removed.assert_not_called()


def test_browser_sessions_do_not_share_transient_state(tmp_path: Path) -> None:
    with fake_backend():
        controller, first = make_workspace(tmp_path)
        second = Session()
        controller.initialise(second)
        controller.toggle_library(first)
        first.remember({"text": "Private draft"})
        assert second.use_library is False
        assert second.drafts == {}


def test_undeclared_chat_ids_are_rejected(tmp_path: Path) -> None:
    with fake_backend():
        controller, session = make_workspace(tmp_path)
        with pytest.raises(BackendError, match="no longer available"):
            controller.select(session, "../documents", None)
        assert session.active_id is None


def test_addressed_chat_is_restored_after_a_backend_outage(tmp_path: Path) -> None:
    with fake_backend() as backend:
        key = backend.create("chat:test", 5, 0.2)["conversation_id"]
        controller = Workspace(upload_root=tmp_path)
        session = Session()
        with (
            patch.object(
                BackendClient, "conversations", side_effect=BackendError("Backend unavailable.")
            ),
            pytest.raises(BackendError),
        ):
            controller.initialise(session, key)
        assert not session.initialised
        assert session.requested_chat == key
        controller.initialise(session)
        assert session.active_id == key
        session.remember({"text": "Still unsent"})
        controller.initialise(session)
        assert session.drafts[key].text == "Still unsent"

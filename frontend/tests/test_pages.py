"""Streamlit interaction tests for persistent conversations and inline documents."""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from streamlit.testing.v1 import AppTest

from api_client import BackendClient, BackendError

ROOT = Path(__file__).parents[1]


class BackendDouble:
    """An inspectable transport double; no Streamlit page performs RAG work."""

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


def test_pages_render_without_emojis_or_dashboard_cards() -> None:
    with fake_backend():
        for path in ["app.py", "pages/1_Documents.py", "pages/2_Settings.py"]:
            app = AppTest.from_file(str(ROOT / path)).run()
            assert not app.exception
        assert app.session_state["top_k"] == 7


def test_text_and_file_are_submitted_from_the_same_composer() -> None:
    with fake_backend() as backend:
        app = AppTest.from_file(str(ROOT / "app.py")).run()
        app.chat_input[0].upload("release.txt", b"Friday release", "text/plain")
        app.chat_input[0].set_value("When is the release?").run()
        assert not app.exception
        assert len(backend.uploads) == 1
        assert len(backend.submissions) == 1
        assert backend.uploads[0][0] == backend.submissions[0][0]
        assert backend.uploads[0][2] == b"Friday release"
        assert any(item.label.startswith("Sources") for item in app.expander)


def test_files_alone_create_a_chat_without_generating_an_answer() -> None:
    with fake_backend() as backend:
        app = AppTest.from_file(str(ROOT / "app.py")).run()
        app.chat_input[0].upload("release.txt", b"Friday", "text/plain").run()
        assert not app.exception
        assert len(backend.chats) == 1
        assert len(backend.uploads) == 1
        assert backend.submissions == []


def test_existing_threads_can_be_selected_without_mixing_messages() -> None:
    with fake_backend() as backend:
        first = backend.create("chat:test", 5, 0.2)["conversation_id"]
        second = backend.create("chat:test", 3, 0.0)["conversation_id"]
        backend.update(first, title="Release planning")
        backend.update(second, title="Backup retention")
        app = AppTest.from_file(str(ROOT / "app.py")).run()
        app.button(key=f"open-{first}").click().run()
        assert app.title[0].value == "Release planning"
        app.chat_input[0].set_value("When is the release?").run()
        app.button(key=f"open-{second}").click().run()
        assert app.title[0].value == "Backup retention"
        assert backend.chats[second]["messages"] == []
        assert app.session_state["active_chat_id"] == second
        assert not app.exception


def test_library_toggle_is_saved_only_on_the_selected_chat() -> None:
    with fake_backend() as backend:
        first = backend.create("chat:test", 5, 0.2)["conversation_id"]
        second = backend.create("chat:test", 5, 0.2)["conversation_id"]
        app = AppTest.from_file(str(ROOT / "app.py"))
        app.query_params["chat"] = first
        app.run()
        app.toggle[0].set_value(True).run()
        assert backend.chats[first]["use_library"] is True
        assert backend.chats[second]["use_library"] is False


def test_failed_submission_keeps_the_same_request_id_for_retry() -> None:
    with fake_backend() as backend:
        backend.fail_send = True
        app = AppTest.from_file(str(ROOT / "app.py")).run()
        app.chat_input[0].set_value("When is the release?").run()
        assert not app.exception
        assert app.error[0].value == "Ollama is temporarily unavailable."
        first_request_id = backend.submissions[0][2]
        backend.fail_send = False
        next(button for button in app.button if button.label == "Retry submission").click().run()
        assert not app.exception
        assert backend.submissions[-1][2] == first_request_id
        assert len(next(iter(backend.chats.values()))["messages"]) == 2


def test_backend_outage_displays_a_recovery_action() -> None:
    with (
        fake_backend(),
        patch.object(
            BackendClient,
            "conversations",
            side_effect=BackendError("Backend unavailable."),
        ),
    ):
        app = AppTest.from_file(str(ROOT / "app.py")).run()
        assert not app.exception
        assert app.error[0].value == "Backend unavailable."
        assert any(button.label == "Try again" for button in app.button)


def test_legacy_session_is_imported_before_chat_navigation() -> None:
    with fake_backend() as backend:
        legacy = [
            {"role": "user", "content": "An earlier question"},
            {"role": "assistant", "content": "An earlier answer", "sources": []},
        ]

        def import_saved(
            conversation_id: str,
            messages: list[dict[str, Any]],
            model: str,
            top_k: int,
            temperature: float,
        ) -> dict[str, Any]:
            created = backend.create(model, top_k, temperature)
            backend.chats[created["conversation_id"]]["messages"] = [
                {**message, "message_id": str(uuid4())} for message in messages
            ]
            return deepcopy(backend.chats[created["conversation_id"]])

        with patch.object(
            BackendClient, "import_conversation", side_effect=import_saved
        ) as imported:
            app = AppTest.from_file(str(ROOT / "app.py"))
            app.session_state.messages = legacy
            app.run()
            assert not app.exception
            assert imported.call_count == 1
            assert len(next(iter(backend.chats.values()))["messages"]) == 2
            app.run()
            assert imported.call_count == 1


def test_failed_drafts_remain_with_their_original_chat() -> None:
    with fake_backend() as backend:
        first = backend.create("chat:test", 5, 0.2)["conversation_id"]
        second = backend.create("chat:test", 5, 0.2)["conversation_id"]
        backend.update(first, title="First chat")
        backend.update(second, title="Second chat")
        app = AppTest.from_file(str(ROOT / "app.py"))
        app.query_params["chat"] = first
        app.run()
        backend.fail_send = True
        app.chat_input[0].set_value("The first question").run()
        app.button(key=f"open-{second}").click().run()
        backend.fail_send = False
        app.chat_input[0].set_value("The second question").run()
        app.button(key=f"open-{first}").click().run()
        assert not app.exception
        assert app.error[0].value == "Ollama is temporarily unavailable."
        assert app.session_state["pending_submissions"][first]["text"] == "The first question"
        assert second not in app.session_state["pending_submissions"]


def test_model_and_library_controls_are_outside_the_scrolling_transcript() -> None:
    with fake_backend() as backend:
        chat_id = backend.create("chat:test", 5, 0.2)["conversation_id"]
        app = AppTest.from_file(str(ROOT / "app.py"))
        app.query_params["chat"] = chat_id
        app.run()
        assert not app.exception
        assert len(app.main.selectbox) == 0
        assert len(app.main.toggle) == 0
        assert len(app.selectbox) == 1
        assert len(app.toggle) == 1
        assert len(app.chat_input) == 1


def test_composer_model_selection_and_chat_options_update_the_same_thread() -> None:
    with fake_backend() as backend:
        chat_id = backend.create("chat:test", 5, 0.2)["conversation_id"]
        other = backend.create("chat:test", 5, 0.2)["conversation_id"]
        with patch.object(
            BackendClient,
            "models",
            return_value={
                "models": ["chat:test", "chat:alternative"],
                "default_model": "chat:test",
                "defaults": {"top_k": 5, "temperature": 0.2, "max_upload_bytes": 20971520},
            },
        ):
            app = AppTest.from_file(str(ROOT / "app.py"))
            app.query_params["chat"] = chat_id
            app.run()
            app.selectbox[0].set_value("chat:alternative").run()
            assert backend.chats[chat_id]["model"] == "chat:alternative"
            app.number_input[0].set_value(3)
            next(button for button in app.button if button.label == "Save changes").click().run()
            assert backend.chats[chat_id]["top_k"] == 3
            assert backend.chats[other]["model"] == "chat:test"
            assert backend.chats[other]["top_k"] == 5
            assert not app.exception


def test_library_choice_in_an_empty_composer_applies_to_the_created_chat() -> None:
    with fake_backend() as backend:
        app = AppTest.from_file(str(ROOT / "app.py")).run()
        app.toggle[0].set_value(True).run()
        assert backend.chats == {}
        app.chat_input[0].set_value("Use the shared library").run()
        assert not app.exception
        assert next(iter(backend.chats.values()))["use_library"] is True
        assert app.session_state["new_chat_use_library"] is False

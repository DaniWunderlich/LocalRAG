"""Sidebar commands preserve the open conversation, drafts and user-authored text."""

from pathlib import Path

import pytest
from test_pages import fake_backend, make_workspace

from api_client import BackendError
from navigation import chat_navigation
from workspace import Session, source_details


def test_manage_and_delete_another_chat_preserves_current_draft(tmp_path: Path) -> None:
    with fake_backend() as backend:
        first = backend.create("chat:test", 5, 0.2)["conversation_id"]
        second = backend.create("chat:test", 5, 0.2)["conversation_id"]
        controller, session = make_workspace(tmp_path)
        controller.select(session, first, None)
        session.remember({"text": "Keep my draft", "files": []})
        session.managed_id = second
        controller.manage_chat(session, "  Planung  ", "  Arbeit  ")
        assert backend.chats[second]["title"] == "Planung"
        assert backend.chats[second]["folder"] == "Arbeit"
        assert session.active_id == first
        assert session.drafts[first].text == "Keep my draft"
        with pytest.raises(BackendError, match="Confirm"):
            controller.delete_managed_chat(session, False)
        controller.delete_managed_chat(session, True)
        assert second not in backend.chats
        assert first in backend.chats
        assert session.active_id == first
        assert session.drafts[first].text == "Keep my draft"


def test_managed_chat_validation_and_removing_folder(tmp_path: Path) -> None:
    with fake_backend() as backend:
        key = backend.create("chat:test", 5, 0.2)["conversation_id"]
        controller, session = make_workspace(tmp_path)
        session.managed_id = key
        for title, folder in [("", "Work"), ("x" * 121, ""), ("Valid", "x" * 81)]:
            with pytest.raises(BackendError):
                controller.manage_chat(session, title, folder)
        controller.manage_chat(session, "Valid", "Work")
        controller.manage_chat(session, "Valid", "")
        assert backend.chats[key]["folder"] == ""
        session.managed_id = "missing"
        with pytest.raises(BackendError, match="no longer available"):
            controller.manage_chat(session, "Valid", "")
        session.managed_id = key
        controller.select(session, key, None)
        controller.delete_managed_chat(session, True)
        assert session.active_id is None
        assert session.conversation is None


def test_grouped_navigation_escapes_names_and_searches_folders() -> None:
    session = Session(
        language="de",
        summaries=[
            {
                "conversation_id": "id-1",
                "title": '<img src=x onerror="bad()">',
                "folder": "<Work>",
                "status": "active",
            },
            {"conversation_id": "id-2", "title": "New chat", "folder": "", "status": "active"},
        ],
    )
    rendered = chat_navigation(session)
    assert "<img" not in rendered
    assert "&lt;Work&gt;" in rendered
    assert "Umbenennen" in rendered and "In Ordner verschieben" in rendered
    assert "New chat" in rendered  # Saved titles remain user data.
    session.chat_query = "work"
    rendered = chat_navigation(session)
    assert "id-1" in rendered and "id-2" not in rendered
    session.chat_query = "missing"
    assert "Keine Chats gefunden." in chat_navigation(session)


def test_source_disclosures_are_localized_without_translating_evidence() -> None:
    sources = [
        {
            "source_id": 1,
            "filename": "Source.txt",
            "page": 2,
            "chunk_index": 0,
            "score": 0.9,
            "text": "Original evidence",
        }
    ]
    rendered = source_details(sources, True, "de")
    assert "Quellen (1)" in rendered and "Seite 2" in rendered
    assert "Ähnlichkeit" in rendered and "Original evidence" in rendered

"""Streamlit smoke tests with a backend double and no external services."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).parents[1]


def test_pages_render_with_session_preferences() -> None:
    models: dict[str, Any] = {
        "models": ["chat:test"],
        "default_model": "",
        "defaults": {"top_k": 7, "temperature": 0.3, "max_upload_bytes": 20971520},
    }
    with (
        patch("api_client.BackendClient.models", return_value=models),
        patch("api_client.BackendClient.documents", return_value=[]),
        patch("api_client.BackendClient.request", return_value={"status": "ready"}),
    ):
        for path in ["app.py", "pages/1_Documents.py", "pages/2_Settings.py"]:
            app = AppTest.from_file(str(ROOT / path)).run(timeout=15)
            assert not app.exception
        assert app.session_state["top_k"] == 7
        assert app.session_state["selected_model"] == "chat:test"


def test_chat_displays_the_returned_source() -> None:
    models = {
        "models": ["chat:test"],
        "default_model": "chat:test",
        "defaults": {"top_k": 5, "temperature": 0.2, "max_upload_bytes": 20971520},
    }
    result = {
        "answer": "The release is on Friday. [Source 1]",
        "sources": [
            {
                "source_id": 1,
                "filename": "release.txt",
                "page": 2,
                "section": None,
                "score": 0.9,
                "chunk_id": "test-chunk",
                "text": "The release is on Friday.",
            }
        ],
    }
    with (
        patch("api_client.BackendClient.models", return_value=models),
        patch("api_client.BackendClient.request", return_value={"status": "ready"}),
        patch("api_client.BackendClient.chat", return_value=result) as chat,
    ):
        app = AppTest.from_file(str(ROOT / "app.py")).run()
        app.chat_input[0].set_value("When is the release?").run()
        assert not app.exception
        assert chat.call_count == 1
        assert len(app.chat_message) == 2
        assert app.expander[0].label == "Source 1: release.txt ? page 2"

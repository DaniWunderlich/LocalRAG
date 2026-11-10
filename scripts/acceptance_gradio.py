"""Exercise the Gradio workspace controller against an isolated real-service stack."""

import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from api_client import BackendClient, BackendError
from workspace import Session, Workspace

STATE = (
    Path(os.environ.get("GRADIO_TEMP_DIR", "/tmp/localrag-uploads")) / "acceptance.json"
)


class InterruptedClient(BackendClient):
    """Simulate a lost response after the backend has already committed the answer."""

    interrupt = True

    def send_message(
        self, conversation_id: str, message: str, request_id: str
    ) -> dict[str, Any]:
        result = super().send_message(conversation_id, message, request_id)
        if self.interrupt:
            self.interrupt = False
            raise BackendError("Simulated lost response after commit.")
        return result


def initialise() -> None:
    """Verify real uploads, idempotent retry, chat isolation and source snapshots."""
    client = InterruptedClient()
    assert client.conversations() == []
    controller = Workspace(client)
    session = Session()
    controller.initialise(session)
    session.model = "granite3.3:8b"
    root = controller.upload_root
    root.mkdir(parents=True, exist_ok=True)
    private = root / "orion-gradio-release.md"
    private.write_text(
        "# Orion release\n\nProject Orion launches on Friday, 20 November 2026. Alice is the release manager. The release window starts at 18:00 UTC and ends at 20:00 UTC. Ben owns rollback. The rollback deadline is 19:30 UTC.",
        encoding="utf-8",
    )
    shared = root / "shared-gradio-handbook.txt"
    shared.write_text(
        "The shared handbook covers the unrelated Project Juniper. Its owner is Clara.",
        encoding="utf-8",
    )
    controller.upload_library(session, [str(shared)])
    try:
        controller.submit(
            session,
            {
                "text": "When does Project Orion launch, and who manages the release?",
                "files": [str(private)],
            },
        )
    except BackendError as error:
        assert str(error) == "Simulated lost response after commit."
    else:
        raise AssertionError("The response interruption was not exercised.")
    first = session.key
    request_id = session.pending[first].request_id
    saved = client.conversation(first)
    assert len(saved["messages"]) == 2
    assert saved["messages"][-1]["sources"]
    controller.retry(session)
    assert len(client.conversation(first)["messages"]) == 2
    assert request_id == client.conversation(first)["messages"][0]["message_id"]
    controller.submit(
        session, {"text": "Who owns rollback, and what is the deadline?", "files": []}
    )
    assert len(client.conversation(first)["messages"]) == 4
    controller.save_settings(
        session, "Orion Gradio acceptance", "granite3.3:8b", 3, 0.15
    )
    snapshot = client.conversation(first)
    controller.new(session, {"text": "Unsent Orion draft", "files": []})
    second = session.key
    assert session.conversation and session.conversation["messages"] == []
    assert session.drafts[first].text == "Unsent Orion draft"
    controller.toggle_library(session)
    controller.save_settings(
        session, "Shared Gradio acceptance", "granite3.3:8b", 4, 0.2
    )
    assert not client.conversation(first)["use_library"]
    assert client.conversation(second)["use_library"]
    assert client.attachments(second) == []
    assert len(client.documents()) == 1
    assert client.attachments(first)[0]["in_library"] is False
    messages = []
    for index in range(1, 13):
        messages.extend(
            [
                {
                    "role": "user",
                    "content": f"Review item {index}: what needs checking before the Orion release?",
                },
                {
                    "role": "assistant",
                    "content": f"Review item {index}: confirm that the document backup can be restored and that the API readiness check succeeds. Alice owns the release decision. Ben owns rollback and confirms that the previous index remains available.\n\nRecord the outcome in the release notes before continuing to the next operational check. The release window is 18:00 to 20:00 UTC."
                    + (
                        "\n\nFinal review complete. The release notes are archived."
                        if index == 12
                        else ""
                    ),
                    "sources": snapshot["messages"][-1]["sources"],
                },
            ]
        )
    long_chat = client.import_conversation(
        str(uuid4()), messages, "granite3.3:8b", 5, 0.2
    )
    client.update_conversation(
        long_chat["conversation_id"], title="Orion visual review", use_library=False
    )
    for index in range(11):
        other = client.create_conversation("granite3.3:8b", 5, 0.2)
        client.update_conversation(
            other["conversation_id"], title=f"Saved research topic {index + 1}"
        )
    STATE.write_text(
        json.dumps(
            {
                "first": first,
                "second": second,
                "snapshot": snapshot,
                "long": long_chat["conversation_id"],
            }
        ),
        encoding="utf-8",
    )
    print(
        "PASS real Gradio controller uploads, grounded turns, lost-response retry, isolation and drafts"
    )
    print("Review URL: http://localhost:18501/?chat=" + long_chat["conversation_id"])


def verify() -> None:
    """Restore saved chats after restart, including with a fresh frontend cache."""
    controller = Workspace()
    if STATE.exists():
        data = json.loads(STATE.read_text(encoding="utf-8"))
        expected = data["snapshot"]
        first, second = data["first"], data["second"]
    else:
        # A recreated frontend has a fresh cache; durable records stay in the backend.
        summaries = controller.client.conversations()
        first = next(
            item["conversation_id"]
            for item in summaries
            if item["title"] == "Orion Gradio acceptance"
        )
        second = next(
            item["conversation_id"]
            for item in summaries
            if item["title"] == "Shared Gradio acceptance"
        )
        expected = None
    session = Session()
    controller.initialise(session, first)
    if expected is not None:
        assert session.conversation == expected
    assert session.conversation is not None
    assert len(session.conversation["messages"]) == 4
    assert session.conversation["model"] == "granite3.3:8b"
    assert session.conversation["top_k"] == 3
    assert session.conversation["temperature"] == 0.15
    assert (
        session.conversation["messages"][-1]["sources"][0]["filename"]
        == "orion-gradio-release.md"
    )
    assert len(session.summaries) >= 14
    assert len(session.documents) == 1
    assert len(session.attachments) == 1
    assert controller.client.conversation(second)["use_library"] is True
    print(
        "PASS saved chats, settings, attachment links and source snapshots survive restart"
    )


if __name__ == "__main__":
    {"initialise": initialise, "verify": verify}[sys.argv[1]]()

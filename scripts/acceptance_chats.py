"""Real-service conversation acceptance using an isolated, disposable stack."""

import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

STATE = Path("/app/data/documents/chat-acceptance.json")


def require(response: httpx.Response, status: int = 200) -> dict[str, Any]:
    """Fail with a useful API error when an acceptance operation is unsuccessful."""
    assert response.status_code == status, response.text
    return response.json()


def initialise(client: httpx.Client) -> None:
    """Check private evidence, grounded follow-ups and a realistic saved chat list."""
    assert client.get("/api/v1/conversations").json() == []
    chat = require(
        client.post("/api/v1/conversations", json={"model": "granite3.3:8b"}), 201
    )
    chat_id = chat["conversation_id"]
    document = require(
        client.post(
            f"/api/v1/conversations/{chat_id}/documents",
            files={
                "file": (
                    "orion-release-notes.md",
                    (
                        b"# Orion release plan\n\n"
                        b"Project Orion launches on Friday, 20 November 2026. Alice is the release manager.\n\n"
                        b"The release window starts at 18:00 UTC and ends at 20:00 UTC. "
                        b"The rollback owner is Ben. The rollback deadline is 19:30 UTC.\n\n"
                        b"## Release checks\n\n"
                        b"Before release, confirm the document backup, run the API health checks "
                        b"and verify that the source index is available. Alice approves the final go-ahead."
                    ),
                    "text/markdown",
                )
            },
        ),
        201,
    )
    assert document["in_library"] is False
    assert client.get("/api/v1/documents").json() == []
    request_id = str(uuid4())
    first = require(
        client.post(
            f"/api/v1/conversations/{chat_id}/messages",
            json={
                "request_id": request_id,
                "message": "When does Project Orion launch, and who manages the release?",
            },
        )
    )
    assert "friday" in first["messages"][-1]["content"].lower()
    assert "alice" in first["messages"][-1]["content"].lower()
    retried = require(
        client.post(
            f"/api/v1/conversations/{chat_id}/messages",
            json={
                "request_id": request_id,
                "message": "When does Project Orion launch, and who manages the release?",
            },
        )
    )
    assert len(retried["messages"]) == 2
    second = require(
        client.post(
            f"/api/v1/conversations/{chat_id}/messages",
            json={
                "request_id": str(uuid4()),
                "message": "Who owns the rollback, and what is the deadline?",
            },
        )
    )
    assert "ben" in second["messages"][-1]["content"].lower()
    assert "19:30" in second["messages"][-1]["content"]
    titles = [
        "Orion release planning",
        "Harbour backup retention",
        "Atlas support hours",
        "Cedar emergency procedures",
        "Document indexing review",
        "November maintenance",
        "Release checklist",
        "Local model comparison",
        "API integration notes",
        "Storage and recovery",
        "Operations handover",
        "Supplier documentation",
        "Network maintenance",
        "Onboarding notes",
    ]
    others = []
    for title in titles[1:]:
        other = require(
            client.post("/api/v1/conversations", json={"model": "granite3.3:8b"}), 201
        )
        require(
            client.patch(
                f"/api/v1/conversations/{other['conversation_id']}",
                json={"title": title},
            )
        )
        others.append(other["conversation_id"])
    require(client.patch(f"/api/v1/conversations/{chat_id}", json={"title": titles[0]}))
    isolated = require(
        client.post(
            f"/api/v1/conversations/{others[0]}/messages",
            json={
                "request_id": str(uuid4()),
                "message": "When does Orion launch?",
            },
        )
    )
    assert isolated["messages"][-1]["sources"] == []
    library = require(
        client.post(
            "/api/v1/documents",
            files={
                "file": (
                    "harbour-backup-policy.txt",
                    b"Harbour backup retention is seven days.",
                    "text/plain",
                )
            },
        ),
        201,
    )
    STATE.write_text(
        json.dumps(
            {
                "primary": chat_id,
                "others": others,
                "document": document["document_id"],
                "library": library["document_id"],
                "snapshot": client.get(f"/api/v1/conversations/{chat_id}").json(),
            }
        ),
        encoding="utf-8",
    )
    print(
        "PASS private inline upload, two grounded turns, idempotency and chat isolation",
        flush=True,
    )
    print(f"REVIEW_URL=http://localhost:18501/?chat={chat_id}", flush=True)


def verify(client: httpx.Client) -> None:
    """Assert saved transcripts, source snapshots and scopes after a restart."""
    state = json.loads(STATE.read_text(encoding="utf-8"))
    restored = require(client.get("/api/v1/conversations/" + state["primary"]))
    assert restored == state["snapshot"]
    assert len(client.get("/api/v1/conversations").json()) == 14
    assert restored["use_library"] is False
    assert len(client.get("/api/v1/documents").json()) == 1
    print(
        "PASS all saved conversations, settings, attachments and sources survive restart"
    )


def cleanup(client: httpx.Client) -> None:
    """Remove only the artificial records named by this acceptance run."""
    state = json.loads(STATE.read_text(encoding="utf-8"))
    for chat_id in [state["primary"], *state["others"]]:
        assert client.delete(f"/api/v1/conversations/{chat_id}").status_code == 204
    assert client.get("/api/v1/conversations").json() == []
    assert client.get("/api/v1/documents/" + state["document"]).status_code == 404
    assert client.get("/api/v1/documents/" + state["library"]).status_code == 200
    assert client.delete("/api/v1/documents/" + state["library"]).status_code == 204
    STATE.unlink()
    print(
        "PASS private attachment cleanup and preservation of shared-library originals"
    )


if __name__ == "__main__":
    with httpx.Client(
        base_url="http://localhost:8000", timeout=600, trust_env=False
    ) as connection:
        {"initialise": initialise, "verify": verify, "cleanup": cleanup}[sys.argv[1]](
            connection
        )

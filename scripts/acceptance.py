"""Run inside an isolated backend container against real Qdrant and local Ollama.

Invoke with initialise, verify or cleanup. The caller restarts the containers
between initialise and verify to test persistence. Never use a populated stack.
"""

import io
import json
import os
import sys
from pathlib import Path
from uuid import UUID

import httpx
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

BASE_URL = "http://localhost:8000"
STATE = Path("/app/data/documents/acceptance.json")
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def make_pdf() -> bytes:
    """Generate a PDF with an actual, extractable text layer."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            ),
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(
        b"BT /F1 12 Tf 20 260 Td (The Cedar emergency assembly point is the north gate.) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def fixtures() -> list[tuple[str, bytes, str]]:
    """Provide four distinct, artificial documents without private information."""
    document = Document()
    document.add_heading("Atlas support", 1)
    document.add_paragraph("The Atlas support desk opens at 09:30 on weekdays.")
    output = io.BytesIO()
    document.save(output)
    return [
        (
            "orion.txt",
            b"Project Orion launches on Friday. The release manager is Alice.",
            "text/plain",
        ),
        (
            "harbour.md",
            b"# Harbour backups\n\nHarbour backups are retained for seven days.",
            "text/markdown",
        ),
        ("atlas.docx", output.getvalue(), DOCX_TYPE),
        ("cedar.pdf", make_pdf(), "application/pdf"),
    ]


def initialise(client: httpx.Client) -> None:
    """Exercise upload, metadata, search and a real grounded chat completion."""
    assert client.get("/api/v1/documents").json() == [], (
        "Acceptance requires an empty test stack."
    )
    ready = client.get("/health/ready")
    assert ready.status_code == 200, ready.text
    models = client.get("/api/v1/models").json()["models"]
    chat_model = os.environ.get("ACCEPTANCE_CHAT_MODEL", "granite3.3:8b")
    assert chat_model in models, "Install or select a local chat model for acceptance."
    documents = []
    for filename, data, content_type in fixtures():
        response = client.post(
            "/api/v1/documents", files={"file": (filename, data, content_type)}
        )
        assert response.status_code == 201, response.text
        meta = response.json()
        assert meta["status"] == "indexed" and meta["chunk_count"] > 0
        documents.append(meta)
        print(f"PASS upload {filename}", flush=True)
    for filename, query, expected in [
        ("orion.txt", "On which day does Project Orion launch?", "Friday"),
        ("harbour.md", "How long are Harbour backups retained?", "seven days"),
        ("atlas.docx", "At what time does the Atlas support desk open?", "09:30"),
        ("cedar.pdf", "Where is the Cedar emergency assembly point?", "north gate"),
    ]:
        response = client.post("/api/v1/search", json={"query": query, "top_k": 1})
        assert response.status_code == 200, response.text
        sources = response.json()
        assert len(sources) == 1 and sources[0]["filename"] == filename, sources
        assert expected in sources[0]["text"]
        print(f"PASS retrieval {filename}", flush=True)
    response = client.post(
        "/api/v1/chat",
        json={
            "message": "On which day does Project Orion launch? Cite the source.",
            "model": chat_model,
            "top_k": 2,
            "temperature": 0,
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert "friday" in result["answer"].lower(), result
    assert result["sources"] and any(
        item["filename"] == "orion.txt" for item in result["sources"]
    )
    assert "[Source " in result["answer"], result
    STATE.write_text(json.dumps(documents), encoding="utf-8")
    print("PASS grounded local chat with inspectable sources", flush=True)


def verify(client: httpx.Client) -> None:
    """Verify documents, originals and retrieval after all containers restart."""
    documents = json.loads(STATE.read_text(encoding="utf-8"))
    assert client.get("/api/v1/documents").json() == list(reversed(documents))
    for meta in documents:
        assert Path("/app/data/documents", str(UUID(meta["document_id"]))).is_file()
    response = client.post(
        "/api/v1/search", json={"query": "When does Project Orion launch?", "top_k": 1}
    )
    assert response.status_code == 200, response.text
    assert response.json()[0]["filename"] == "orion.txt"
    print("PASS registry, originals and Qdrant persistence after restart", flush=True)


def cleanup(client: httpx.Client) -> None:
    """Remove only the artificial fixtures recorded by this acceptance run."""
    documents = json.loads(STATE.read_text(encoding="utf-8"))
    for meta in documents:
        response = client.delete("/api/v1/documents/" + str(UUID(meta["document_id"])))
        assert response.status_code == 204, response.text
        assert not Path("/app/data/documents", meta["document_id"]).exists()
    assert client.get("/api/v1/documents").json() == []
    assert client.post("/api/v1/search", json={"query": "Orion"}).json() == []
    count = httpx.post(
        "http://qdrant:6333/collections/rag_documents/points/count",
        json={"exact": True},
        trust_env=False,
    ).json()["result"]["count"]
    assert count == 0, count
    STATE.unlink()
    print("PASS deletion of metadata, originals and all Qdrant points", flush=True)


if __name__ == "__main__":
    phase = sys.argv[1]
    with httpx.Client(base_url=BASE_URL, timeout=600, trust_env=False) as connection:
        {"initialise": initialise, "verify": verify, "cleanup": cleanup}[phase](
            connection
        )

"""End-to-end API contracts, rollback, retries and safe failures."""

import io
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from docx import Document

from rag.errors import AppError
from rag.storage.documents import DocumentRegistry
from tests.conftest import Harness, pdf_bytes

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def upload(harness: Harness, data: bytes = b"The release is on Friday.") -> dict[str, object]:
    """Upload a plain text document and require a complete index."""
    response = harness.client.post(
        "/api/v1/documents", files={"file": ("release.txt", data, "text/plain")}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_complete_document_search_chat_delete(harness: Harness) -> None:
    meta = upload(harness)
    assert meta["status"] == "indexed"
    document_id = meta["document_id"]
    assert harness.client.get(f"/api/v1/documents/{document_id}").json() == meta
    result = harness.client.post(
        "/api/v1/search", json={"query": "When is the release?", "top_k": 1}
    )
    assert result.status_code == 200
    source = result.json()[0]
    assert source["filename"] == "release.txt"
    assert source["document_id"] == document_id
    assert source["text"] == "The release is on Friday."
    chat = harness.client.post("/api/v1/chat", json={"message": "When?", "temperature": 0})
    assert chat.status_code == 200
    assert chat.json()["sources"][0]["source_id"] == 1
    chat_body = next(
        body for path, body in reversed(harness.ollama.requests) if path == "/api/chat"
    )
    assert chat_body["options"]["temperature"] == 0
    assert chat_body["stream"] is False
    assert source["text"] in chat_body["messages"][1]["content"]
    response = harness.client.delete(f"/api/v1/documents/{document_id}")
    assert response.status_code == 204
    assert harness.client.get("/api/v1/documents").json() == []
    assert not harness.services.registry.file_path(UUID(str(document_id))).exists()
    assert harness.client.post("/api/v1/search", json={"query": "Friday"}).json() == []


@pytest.mark.parametrize(
    "filename,content_type",
    [
        ("test.txt", "text/plain"),
        ("test.md", "text/markdown"),
        ("test.PDF", "application/pdf"),
        ("test.docx", DOCX_TYPE),
    ],
)
def test_supported_formats(harness: Harness, filename: str, content_type: str) -> None:
    data = b"# Release\n\nThe release is on Friday."
    if filename.endswith("PDF"):
        data = pdf_bytes()
    if filename.endswith("docx"):
        document = Document()
        document.add_heading("Release", level=1)
        document.add_paragraph("The release is on Friday.")
        table = document.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "Owner"
        table.cell(0, 1).text = "Operations"
        output = io.BytesIO()
        document.save(output)
        data = output.getvalue()
    response = harness.client.post(
        "/api/v1/documents", files={"file": (filename, data, content_type)}
    )
    assert response.status_code == 201, response.text
    sources = harness.client.post("/api/v1/search", json={"query": "Friday"}).json()
    assert any("Friday" in source["text"] for source in sources)
    if content_type == "application/pdf":
        assert sources[0]["page"] == 1
    if content_type == DOCX_TYPE:
        assert any("Operations" in source["text"] for source in sources)


@pytest.mark.parametrize(
    "filename,data,content_type,status",
    [
        ("empty.txt", b"", "text/plain", 422),
        ("invalid.txt", b"\xff", "text/plain", 422),
        ("binary.txt", b"binary\x00text", "text/plain", 422),
        ("file.exe", b"plain text", "text/plain", 415),
        ("file.pdf", b"plain text", "application/pdf", 422),
        ("file.docx", b"PKnot-a-zip", DOCX_TYPE, 422),
        ("file.txt", b"hello", "image/png", 415),
        ("blank.txt", b" \n\t", "text/plain", 422),
        ("scan.pdf", pdf_bytes(None), "application/pdf", 422),
    ],
)
def test_invalid_uploads(
    harness: Harness,
    filename: str,
    data: bytes,
    content_type: str,
    status: int,
) -> None:
    response = harness.client.post(
        "/api/v1/documents", files={"file": (filename, data, content_type)}
    )
    assert response.status_code == status
    assert all(
        meta["status"] == "failed" for meta in harness.client.get("/api/v1/documents").json()
    )


def test_duplicate_hash_and_path_sanitisation(harness: Harness) -> None:
    data = b"Friday release"
    first = harness.client.post(
        "/api/v1/documents", files={"file": ("../../outside.txt", data, "text/plain")}
    )
    assert first.status_code == 201
    assert first.json()["filename"] == "outside.txt"
    second = harness.client.post(
        "/api/v1/documents", files={"file": ("renamed.md", data, "text/markdown")}
    )
    assert second.status_code == 409
    assert len(harness.client.get("/api/v1/documents").json()) == 1
    original = harness.services.registry.file_path(UUID(first.json()["document_id"]))
    assert original.read_bytes() == data
    assert original.parent == harness.services.registry.path


def test_size_limit(harness: Harness) -> None:
    harness.services.settings.max_upload_bytes = 8
    response = harness.client.post(
        "/api/v1/documents", files={"file": ("large.txt", b"x" * 9, "text/plain")}
    )
    assert response.status_code == 413
    assert harness.client.get("/api/v1/documents").json() == []


def test_failed_embedding_can_be_retried(harness: Harness) -> None:
    harness.ollama.fail_embeddings = True
    response = harness.client.post(
        "/api/v1/documents", files={"file": ("retry.txt", b"Friday", "text/plain")}
    )
    assert response.status_code == 503
    assert "secret" not in response.text
    failed = harness.client.get("/api/v1/documents").json()[0]
    assert failed["status"] == "failed"
    assert failed["chunk_count"] == 0
    harness.ollama.fail_embeddings = False
    retried = upload(harness, b"Friday")
    assert retried["document_id"] == failed["document_id"]
    assert len(harness.client.get("/api/v1/documents").json()) == 1


def test_partial_upsert_is_rolled_back(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    original = harness.services.qdrant.upsert_chunks

    async def fail_after_write(*args: object, **kwargs: object) -> None:
        await original(*args, **kwargs)  # type: ignore[arg-type]
        raise AppError("Injected database failure.")

    monkeypatch.setattr(harness.services.qdrant, "upsert_chunks", fail_after_write)
    response = harness.client.post(
        "/api/v1/documents", files={"file": ("fail.txt", b"Friday", "text/plain")}
    )
    assert response.status_code == 503
    count = harness.client.portal.call(  # type: ignore[union-attr]
        harness.services.qdrant.client.count,
        "test_documents",
    )
    assert count.count == 0
    assert harness.client.get("/api/v1/documents").json()[0]["status"] == "failed"


def test_failed_deletion_stays_hidden_and_can_be_retried(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    meta = upload(harness)
    original = harness.services.qdrant.delete_document
    monkeypatch.setattr(
        harness.services.qdrant, "delete_document", AsyncMock(side_effect=AppError("Unavailable."))
    )
    assert harness.client.delete(f"/api/v1/documents/{meta['document_id']}").status_code == 503
    assert harness.client.get("/api/v1/documents").json()[0]["status"] == "deleting"
    assert harness.client.post("/api/v1/search", json={"query": "Friday"}).json() == []
    monkeypatch.setattr(harness.services.qdrant, "delete_document", original)
    assert harness.client.delete(f"/api/v1/documents/{meta['document_id']}").status_code == 204


def test_model_digest_change_is_rejected_even_with_same_dimension(harness: Harness) -> None:
    upload(harness)
    harness.ollama.digest = "embedding-revision-b"
    response = harness.client.post("/api/v1/search", json={"query": "Friday"})
    assert response.status_code == 409
    assert response.json()["code"] == "embedding_mismatch"
    assert harness.client.get("/health/ready").status_code == 503


def test_missing_index_is_not_reported_as_empty_results(harness: Harness) -> None:
    upload(harness)
    harness.client.portal.call(harness.services.qdrant.client.delete_collection, "test_documents")  # type: ignore[union-attr]
    response = harness.client.post("/api/v1/search", json={"query": "Friday"})
    assert response.status_code == 409
    assert response.json()["code"] == "index_missing"


def test_upload_does_not_silently_replace_a_missing_index(harness: Harness) -> None:
    upload(harness)
    harness.client.portal.call(harness.services.qdrant.client.delete_collection, "test_documents")  # type: ignore[union-attr]
    response = harness.client.post(
        "/api/v1/documents", files={"file": ("another.txt", b"Another document.", "text/plain")}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "index_missing"


def test_no_documents_calls_general_generation(harness: Harness) -> None:
    response = harness.client.post("/api/v1/chat", json={"message": "When?"})
    assert response.status_code == 200
    assert response.json()["sources"] == []
    assert response.json()["answer"] == harness.ollama.general_answer
    calls = [body for path, body in harness.ollama.requests if path == "/api/chat"]
    assert len(calls) == 1
    assert calls[0]["messages"][-1]["content"] == "When?"
    assert "general knowledge" in calls[0]["messages"][0]["content"]
    assert not any(path == "/api/embed" for path, _ in harness.ollama.requests)


def test_unknown_source_citation_is_rejected(harness: Harness) -> None:
    upload(harness)
    harness.ollama.answer = "Friday [Source 99]"
    response = harness.client.post("/api/v1/chat", json={"message": "When?"})
    assert response.status_code == 502
    assert response.json()["code"] == "invalid_citation"


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/v1/search", {"query": "  "}),
        ("/api/v1/search", {"query": "Friday", "top_k": 21}),
        ("/api/v1/chat", {"message": "Friday", "temperature": 2}),
        ("/api/v1/chat", {"message": "Friday", "unexpected": "secret"}),
    ],
)
def test_request_validation_is_safe(harness: Harness, path: str, body: dict[str, object]) -> None:
    response = harness.client.post(path, json=body)
    assert response.status_code == 422
    assert "secret" not in response.text


def test_health_and_model_discovery(harness: Harness) -> None:
    assert harness.client.get("/health/live").status_code == 200
    assert harness.client.get("/health/ready").status_code == 200
    assert harness.client.get("/api/v1/models").json()["models"] == ["chat:test"]
    assert harness.client.get(f"/api/v1/documents/{uuid4()}").status_code == 404
    assert harness.client.get("/api/v1/documents/../../registry.json").status_code == 404


def test_registry_reload_keeps_metadata(harness: Harness) -> None:
    meta = upload(harness)
    restored = DocumentRegistry(harness.services.registry.path)
    assert restored.get(UUID(str(meta["document_id"]))).model_dump(mode="json") == meta  # type: ignore[union-attr]


def test_interrupted_upload_is_recovered(harness: Harness) -> None:
    meta = upload(harness)
    record = harness.services.registry.get(UUID(str(meta["document_id"])))
    assert record is not None
    harness.services.registry.save(record.model_copy(update={"status": "processing"}))
    harness.client.portal.call(harness.services.recover)  # type: ignore[union-attr]
    recovered = harness.client.get("/api/v1/documents").json()[0]
    assert recovered["status"] == "failed"
    assert recovered["chunk_count"] == 0
    assert "interrupted" in recovered["error"]

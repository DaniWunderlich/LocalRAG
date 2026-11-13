"""Offline API fixtures using mocked Ollama HTTP and ephemeral local Qdrant."""

import io
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from qdrant_client import AsyncQdrantClient

from rag.config import Settings
from rag.main import create_app
from rag.providers.ollama import OllamaClient
from rag.providers.qdrant import QdrantProvider
from rag.services import Services
from rag.storage.documents import DocumentRegistry


@dataclass
class OllamaStub:
    """Exercise the real HTTP adapter without loading or downloading an LLM."""

    digest: str = "embedding-revision-a"
    fail_embeddings: bool = False
    answer: str = "The release is on Friday. [Source 1]"
    general_answer: str = "A general answer from the local model."
    requests: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def respond(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        self.requests.append((request.url.path, body))
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "embed:test", "digest": self.digest},
                        {"name": "chat:test", "digest": "chat-revision-a"},
                    ]
                },
            )
        if request.url.path == "/api/show":
            capability = "embedding" if body["model"] == "embed:test" else "completion"
            return httpx.Response(
                200,
                json={
                    "capabilities": [capability],
                    "model_info": {"test.context_length": 8192},
                },
            )
        if request.url.path == "/api/embed":
            if self.fail_embeddings:
                return httpx.Response(500, json={"error": "secret upstream text"})
            return httpx.Response(
                200,
                json={
                    "embeddings": [
                        [
                            float(text.lower().count("friday") + 1),
                            float(text.lower().count("monday")),
                            1.0,
                        ]
                        for text in body["input"]
                    ]
                },
            )
        if request.url.path == "/api/chat":
            grounded = body["messages"][-1]["content"].startswith(
                "Document excerpts (JSON records):"
            )
            return httpx.Response(
                200, json={"message": {"content": self.answer if grounded else self.general_answer}}
            )
        return httpx.Response(404)


@dataclass
class Harness:
    """An isolated application together with inspectable service adapters."""

    client: TestClient
    services: Services
    ollama: OllamaStub


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    """Create fresh metadata, vectors and HTTP state for every test."""
    config = Settings(
        _env_file=None,
        document_storage_path=tmp_path,
        ollama_embedding_model="embed:test",
        ollama_chat_model="chat:test",
        rag_chunk_size=32,
        rag_chunk_overlap=4,
    )
    stub = OllamaStub()
    bundle = Services(
        config,
        DocumentRegistry(tmp_path),
        OllamaClient("http://ollama.test", transport=httpx.MockTransport(stub.respond)),
        QdrantProvider("http://qdrant.test", "test_documents", AsyncQdrantClient(":memory:")),
    )
    with TestClient(create_app(services=bundle)) as client:
        yield Harness(client, bundle, stub)


def pdf_bytes(text: str | None = "The release is on Friday.") -> bytes:
    """Build a small text-layer PDF using the existing PDF dependency."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    if text:
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
        stream.set_data(f"BT /F1 12 Tf 20 260 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()

"""Provider boundary validation and embedding compatibility checks."""

import httpx
import pytest
from qdrant_client import AsyncQdrantClient

from rag.errors import AppError
from rag.providers.ollama import ModelInfo, OllamaClient
from rag.providers.qdrant import QdrantProvider


@pytest.mark.parametrize("vectors", [[], [[]], [[0, 0]], [[1, 2], [1, 2]], [[float("nan"), 1]]])
async def test_invalid_embedding_responses(vectors: list[list[float]]) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if any(any(value != value for value in vector) for vector in vectors):
            return httpx.Response(
                200,
                content=b'{"embeddings":[[NaN,1]]}',
                headers={"content-type": "application/json"},
            )
        return httpx.Response(200, json={"embeddings": vectors})

    client = OllamaClient("http://test", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(AppError, match="invalid embeddings"):
            await client.embed("embed:test", ["text"])
    finally:
        await client.close()


async def test_connection_error_does_not_disclose_endpoint() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret-endpoint", request=request)

    client = OllamaClient("http://secret-endpoint", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(AppError) as caught:
            await client.tags()
        assert "secret" not in caught.value.message
    finally:
        await client.close()


async def test_remote_completion_model_is_rejected() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "remote:test", "digest": "digest"}]}
            )
        return httpx.Response(
            200, json={"capabilities": ["completion"], "remote_host": "https://example.com"}
        )

    client = OllamaClient("http://test", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(AppError) as caught:
            await client.model_info("remote:test", "completion")
        assert caught.value.code == "remote_model"
    finally:
        await client.close()


async def test_dimension_mismatch_is_rejected() -> None:
    provider = QdrantProvider("", "test", AsyncQdrantClient(":memory:"))
    info = ModelInfo("embed:test", "digest", 8192)
    try:
        await provider.ensure_collection(info, 3)
        with pytest.raises(AppError) as caught:
            await provider.ensure_collection(info, 4)
        assert caught.value.code == "embedding_mismatch"
    finally:
        await provider.close()

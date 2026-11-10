"""Small asynchronous adapter for Ollama's local HTTP API."""

import logging
import math
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from rag.errors import AppError

logger = logging.getLogger(__name__)


class ModelTag(BaseModel):
    """An installed model and its content-addressed identity."""

    name: str
    digest: str = Field(min_length=1)


class TagsResponse(BaseModel):
    """Validate the model list before using upstream data."""

    models: list[ModelTag]


class ShowResponse(BaseModel):
    """Relevant model metadata, including remote execution markers."""

    capabilities: list[str] = Field(default_factory=list)
    model_info: dict[str, Any] = Field(default_factory=dict)
    remote_host: str | None = None
    remote_model: str | None = None


class EmbedResponse(BaseModel):
    """Validate embedding count and values at the provider boundary."""

    embeddings: list[list[float]]


@dataclass(frozen=True)
class ModelInfo:
    """Verified local model identity and native context limit."""

    name: str
    digest: str
    context_length: int


class OllamaClient:
    """Own a reusable HTTP connection pool; never pull models automatically."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 180,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout, connect=5),
            transport=transport,
            trust_env=False,
        )

    async def close(self) -> None:
        """Release pooled connections at application shutdown."""
        await self.http.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self.http.request(method, path, **kwargs)
            response.raise_for_status()
            value: Any = response.json()
            if not isinstance(value, dict):
                raise ValueError("Expected an object.")
            return value
        except httpx.HTTPStatusError as exc:
            logger.warning("ollama_request_failed", extra={"status_code": exc.response.status_code})
            if exc.response.status_code == 404:
                raise AppError(
                    "The selected Ollama model is not installed. Install it locally first.",
                    422,
                    "model_not_found",
                ) from exc
            raise AppError("Ollama rejected the request. Check the local service logs.") from exc
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("ollama_unavailable", extra={"error_type": type(exc).__name__})
            raise AppError("Ollama is unavailable or returned an invalid response.") from exc

    async def tags(self) -> list[ModelTag]:
        """Return installed model names and digests."""
        try:
            return TagsResponse.model_validate(await self._request("GET", "/api/tags")).models
        except ValidationError as exc:
            raise AppError("Ollama returned an invalid model list.") from exc

    async def model_info(
        self, name: str, capability: Literal["embedding", "completion"]
    ) -> ModelInfo:
        """Reject remote models and identify updates even when a tag is unchanged."""
        tags = await self.tags()
        canonical = name if ":" in name else name + ":latest"
        tag = next((item for item in tags if item.name in {name, canonical}), None)
        if tag is None:
            raise AppError("The selected model is not installed locally.", 422, "model_not_found")
        try:
            data = ShowResponse.model_validate(
                await self._request("POST", "/api/show", json={"model": tag.name})
            )
        except ValidationError as exc:
            raise AppError("Ollama returned invalid model information.") from exc
        if data.remote_host or data.remote_model or tag.name.endswith((":cloud", "-cloud")):
            raise AppError(
                "Remote Ollama models are disabled for this local application.", 422, "remote_model"
            )
        if capability not in data.capabilities:
            raise AppError(
                f"The selected model does not support {capability}.", 422, "model_capability"
            )
        lengths = [
            value
            for key, value in data.model_info.items()
            if key.endswith(".context_length") and isinstance(value, int) and value > 0
        ]
        return ModelInfo(tag.name, tag.digest, min(lengths) if lengths else 2048)

    async def list_models(self) -> list[str]:
        """Expose only locally installed completion models."""
        result = []
        for tag in await self.tags():
            try:
                info = await self.model_info(tag.name, "completion")
                result.append(info.name)
            except AppError as exc:
                if exc.code not in {"remote_model", "model_capability"}:
                    raise
        return sorted(result)

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        """Generate complete embeddings and reject truncation or malformed vectors."""
        try:
            data = EmbedResponse.model_validate(
                await self._request(
                    "POST",
                    "/api/embed",
                    json={"model": model, "input": texts, "truncate": False},
                )
            )
            vectors = data.embeddings
            if len(vectors) != len(texts) or not vectors:
                raise ValueError("Unexpected embedding count.")
            dimension = len(vectors[0])
            if not dimension or any(
                len(vector) != dimension
                or not all(math.isfinite(value) for value in vector)
                or not any(vector)
                for vector in vectors
            ):
                raise ValueError("Invalid embedding vector.")
            return vectors
        except (ValidationError, ValueError) as exc:
            raise AppError("Ollama returned invalid embeddings.") from exc

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        context_length: int,
        answer_tokens: int,
    ) -> str:
        """Request one bounded, non-streaming answer."""
        data = await self._request(
            "POST",
            "/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_ctx": context_length,
                    "num_predict": answer_tokens,
                },
            },
        )
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise AppError("Ollama returned an empty or invalid answer.")
        return content.strip()

    async def ping(self) -> bool:
        """Check service availability without loading a model."""
        try:
            await self.tags()
            return True
        except AppError:
            return False

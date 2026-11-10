"""Typed Qdrant operations with an embedding identity in the vector schema."""

import hashlib
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid5

from qdrant_client import AsyncQdrantClient, models

from rag.errors import AppError
from rag.models import Chunk, DocumentMeta, Source
from rag.providers.ollama import ModelInfo

logger = logging.getLogger(__name__)


@contextmanager
def translate_errors() -> Iterator[None]:
    """Prevent database URLs, response bodies and payloads reaching API errors."""
    try:
        yield
    except AppError:
        raise
    except Exception as exc:
        logger.warning("qdrant_request_failed", extra={"error_type": type(exc).__name__})
        raise AppError("Qdrant is unavailable or the index could not be accessed.") from exc


def vector_name(info: ModelInfo) -> str:
    """Tie a collection to the model name and digest, including same-size changes."""
    identity = hashlib.sha256(f"{info.name}:{info.digest}".encode()).hexdigest()
    return "embedding_" + identity


class QdrantProvider:
    """Manage a single cosine collection using a named, content-addressed vector."""

    def __init__(
        self,
        url: str,
        collection: str,
        client: AsyncQdrantClient | None = None,
    ) -> None:
        self.client = client if client is not None else AsyncQdrantClient(url=url, timeout=10)
        self.collection = collection

    async def close(self) -> None:
        """Close the underlying database client."""
        await self.client.close()

    async def exists(self) -> bool:
        """Check whether the active collection has been created."""
        with translate_errors():
            return await self.client.collection_exists(self.collection)

    async def ensure_collection(self, info: ModelInfo, dimension: int, create: bool = True) -> bool:
        """Create or validate the model identity, vector size and cosine metric."""
        with translate_errors():
            name = vector_name(info)
            if not await self.exists():
                if not create:
                    return False
                await self.client.create_collection(
                    self.collection,
                    vectors_config={
                        name: models.VectorParams(size=dimension, distance=models.Distance.COSINE)
                    },
                )
            collection = await self.client.get_collection(self.collection)
            vectors = collection.config.params.vectors
            if not isinstance(vectors, dict) or set(vectors) != {name}:
                raise AppError(
                    "The index belongs to another embedding model or model revision. "
                    "Restore the previous model or rebuild into a new collection.",
                    409,
                    "embedding_mismatch",
                )
            if vectors[name].size != dimension or vectors[name].distance != models.Distance.COSINE:
                raise AppError(
                    "The index vector configuration is incompatible.", 409, "embedding_mismatch"
                )
            return True

    async def check_identity(self, info: ModelInfo) -> bool:
        """Validate an existing index without loading the embedding model for a probe."""
        with translate_errors():
            if not await self.exists():
                return False
            collection = await self.client.get_collection(self.collection)
            vectors = collection.config.params.vectors
            name = vector_name(info)
            if (
                not isinstance(vectors, dict)
                or set(vectors) != {name}
                or vectors[name].distance != models.Distance.COSINE
            ):
                raise AppError(
                    "The active index uses another embedding configuration.",
                    409,
                    "embedding_mismatch",
                )
            return True

    async def upsert_chunks(
        self,
        meta: DocumentMeta,
        chunks: list[Chunk],
        vectors: list[list[float]],
        info: ModelInfo,
    ) -> None:
        """Store a bounded batch; deterministic IDs make retries idempotent."""
        with translate_errors():
            points = [
                models.PointStruct(
                    id=str(uuid5(meta.document_id, str(chunk.chunk_index))),
                    vector={vector_name(info): vector},
                    payload={
                        **chunk.model_dump(exclude={"token_count"}),
                        "document_id": str(meta.document_id),
                        "filename": meta.filename,
                        "content_hash": meta.sha256,
                        "embedding_model": info.name,
                        "embedding_digest": info.digest,
                    },
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
            await self.client.upsert(self.collection, points=points, wait=True)

    async def search(
        self,
        vector: list[float],
        top_k: int,
        info: ModelInfo,
        document_ids: list[UUID],
    ) -> list[Source]:
        """Search only documents committed as indexed in the local registry."""
        if not document_ids:
            return []
        with translate_errors():
            result = await self.client.query_points(
                self.collection,
                query=vector,
                using=vector_name(info),
                limit=top_k,
                with_payload=True,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchAny(any=[str(item) for item in document_ids]),
                        )
                    ]
                ),
            )
            return [
                Source.model_validate(
                    {
                        **(point.payload or {}),
                        "score": point.score,
                        "chunk_id": str(point.id),
                    }
                )
                for point in result.points
            ]

    async def delete_document(self, document_id: UUID) -> None:
        """Wait for all matching points to be removed; missing collections are safe."""
        with translate_errors():
            if await self.exists():
                await self.client.delete(
                    self.collection,
                    wait=True,
                    points_selector=models.FilterSelector(
                        filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="document_id",
                                    match=models.MatchValue(value=str(document_id)),
                                ),
                            ]
                        )
                    ),
                )

    async def ping(self) -> bool:
        """Check connectivity without modifying the collection."""
        try:
            with translate_errors():
                await self.client.get_collections()
            return True
        except AppError:
            return False

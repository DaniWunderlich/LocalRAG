"""Orchestrate ingestion with durable status and compensating vector deletion."""

import asyncio
import logging

from rag.config import Settings
from rag.errors import AppError
from rag.ingestion.chunker import chunk_pages
from rag.ingestion.parser import extract_text
from rag.models import DocumentMeta
from rag.providers.ollama import OllamaClient
from rag.providers.qdrant import QdrantProvider
from rag.storage.documents import DocumentRegistry

logger = logging.getLogger(__name__)


async def index_document(
    meta: DocumentMeta,
    registry: DocumentRegistry,
    ollama: OllamaClient,
    qdrant: QdrantProvider,
    settings: Settings,
) -> DocumentMeta:
    """Expose a document to retrieval only after all batches have been committed."""
    try:
        pages = await asyncio.to_thread(
            extract_text,
            registry.file_path(meta.document_id),
            meta.content_type,
        )
        chunks = await asyncio.to_thread(
            chunk_pages,
            pages,
            settings.rag_chunk_size,
            settings.rag_chunk_overlap,
        )
        info = await ollama.model_info(settings.ollama_embedding_model, "embedding")
        await qdrant.delete_document(meta.document_id)
        can_create = not any(item.status == "indexed" for item in registry.list())
        for offset in range(0, len(chunks), 32):
            batch = chunks[offset : offset + 32]
            vectors = await ollama.embed(info.name, [chunk.text for chunk in batch])
            if not await qdrant.ensure_collection(info, len(vectors[0]), create=can_create):
                raise AppError(
                    "The document index is missing. Rebuild it from the original documents.",
                    409,
                    "index_missing",
                )
            can_create = False
            await qdrant.upsert_chunks(meta, batch, vectors, info)
        current = await ollama.model_info(settings.ollama_embedding_model, "embedding")
        if current.digest != info.digest:
            raise AppError(
                "The embedding model changed during indexing. Retry the upload.",
                409,
                "embedding_mismatch",
            )
        result = meta.model_copy(update={"status": "indexed", "chunk_count": len(chunks)})
        registry.save(result)
        logger.info(
            "document_indexed",
            extra={"document_id": str(meta.document_id), "chunk_count": len(chunks)},
        )
        return result
    except Exception as exc:
        error = exc if isinstance(exc, AppError) else AppError("Document indexing failed.")
        cleanup_failed = False
        try:
            await qdrant.delete_document(meta.document_id)
        except AppError:
            cleanup_failed = True
        message = error.message
        if cleanup_failed:
            message += (
                " Index cleanup is pending; retry the upload or deletion when Qdrant is available."
            )
        registry.save(
            meta.model_copy(update={"status": "failed", "error": message, "chunk_count": 0})
        )
        logger.warning(
            "document_indexing_failed",
            extra={
                "document_id": str(meta.document_id),
                "error_code": error.code,
                "cleanup_pending": cleanup_failed,
            },
        )
        raise error from exc

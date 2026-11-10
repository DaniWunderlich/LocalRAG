"""Independent retrieval and exact, budgeted source context assembly."""

import json
import logging
from time import perf_counter
from uuid import UUID

from rag.config import Settings
from rag.errors import AppError
from rag.ingestion.chunker import count_tokens
from rag.models import Source
from rag.providers.ollama import OllamaClient
from rag.providers.qdrant import QdrantProvider
from rag.storage.documents import DocumentRegistry

logger = logging.getLogger(__name__)


async def retrieve_chunks(
    query: str,
    top_k: int,
    ollama: OllamaClient,
    qdrant: QdrantProvider,
    registry: DocumentRegistry,
    settings: Settings,
    document_ids: set[UUID] | None = None,
) -> list[Source]:
    """Embed a question and search only successfully indexed document IDs."""
    started = perf_counter()
    ids = [
        meta.document_id
        for meta in registry.list()
        if meta.status == "indexed"
        and (meta.document_id in document_ids if document_ids is not None else meta.in_library)
    ]
    if not ids:
        return []
    info = await ollama.model_info(settings.ollama_embedding_model, "embedding")
    vectors = await ollama.embed(info.name, [query])
    if not await qdrant.ensure_collection(info, len(vectors[0]), create=False):
        raise AppError(
            "The document index is missing. Rebuild it from the original documents.",
            409,
            "index_missing",
        )
    sources = await qdrant.search(vectors[0], top_k, info, ids)
    current = await ollama.model_info(settings.ollama_embedding_model, "embedding")
    if current.digest != info.digest:
        raise AppError(
            "The embedding model changed during retrieval. Retry the request.",
            409,
            "embedding_mismatch",
        )
    logger.info(
        "retrieval_completed",
        extra={
            "duration_ms": round((perf_counter() - started) * 1000),
            "result_count": len(sources),
        },
    )
    return sources


def assemble_context(chunks: list[Source], token_budget: int) -> tuple[str, list[Source]]:
    """Fit complete excerpts and their labels, retaining only sources actually sent."""
    blocks: list[str] = []
    sources: list[Source] = []
    for chunk in chunks:
        source = chunk.model_copy(update={"source_id": len(sources) + 1})
        block = json.dumps(
            {
                "label": f"Source {source.source_id}",
                "filename": source.filename,
                "page": source.page,
                "section": source.section,
                "chunk_id": source.chunk_id,
                "text": source.text,
            },
            ensure_ascii=False,
        )
        candidate = "\n".join([*blocks, block])
        if count_tokens(candidate) <= token_budget:
            blocks.append(block)
            sources.append(source)
    return "\n".join(blocks), sources

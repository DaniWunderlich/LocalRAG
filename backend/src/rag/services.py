"""Application-scoped clients and serialised document mutations."""

import asyncio
import logging
from dataclasses import dataclass, field

from fastapi import Request

from rag.config import Settings
from rag.errors import AppError
from rag.providers.ollama import OllamaClient
from rag.providers.qdrant import QdrantProvider
from rag.storage.documents import DocumentRegistry

logger = logging.getLogger(__name__)


@dataclass
class Services:
    """Share one registry and one operation lock within a single backend process."""

    settings: Settings
    registry: DocumentRegistry
    ollama: OllamaClient
    qdrant: QdrantProvider
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def recover(self) -> None:
        """Hide interrupted operations and attempt safe, repeatable cleanup."""
        for meta in self.registry.list():
            if meta.status == "processing":
                meta = meta.model_copy(
                    update={
                        "status": "failed",
                        "chunk_count": 0,
                        "error": "Indexing was interrupted. Re-upload the same file to retry.",
                    }
                )
                self.registry.save(meta)
            if meta.status in {"failed", "deleting"}:
                try:
                    await self.qdrant.delete_document(meta.document_id)
                    if meta.status == "deleting":
                        self.registry.file_path(meta.document_id).unlink(missing_ok=True)
                        self.registry.delete(meta.document_id)
                except AppError, OSError:
                    logger.warning(
                        "document_cleanup_pending", extra={"document_id": str(meta.document_id)}
                    )


def get_services(request: Request) -> Services:
    """Resolve the application bundle through a replaceable FastAPI dependency."""
    services: Services = request.app.state.services
    return services

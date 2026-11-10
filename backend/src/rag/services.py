"""Application-scoped clients and serialised document mutations."""

import asyncio
import logging
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import Request

from rag.config import Settings
from rag.errors import AppError
from rag.models import Conversation
from rag.providers.ollama import OllamaClient
from rag.providers.qdrant import QdrantProvider
from rag.storage.conversations import ConversationStore
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
    chats: ConversationStore = field(init=False)

    def __post_init__(self) -> None:
        """Keep chat transcripts on the same configured persistent volume."""
        self.chats = ConversationStore(self.registry.path)

    async def remove_private_document(self, document_id: UUID, excluded_chat: UUID) -> None:
        """Remove unshared private originals; preserve any shared-library evidence."""
        meta = self.registry.get(document_id)
        if meta is None or meta.in_library:
            return
        if any(
            item.conversation_id != excluded_chat and document_id in item.document_ids
            for item in self.chats.all()
        ):
            return
        self.registry.save(meta.model_copy(update={"status": "deleting"}))
        await self.qdrant.delete_document(document_id)
        self.registry.file_path(document_id).unlink(missing_ok=True)
        self.registry.delete(document_id)

    async def delete_conversation(self, conversation: Conversation) -> None:
        """Retain a deletion marker until all unshared attachments are removed."""
        self.chats.save(conversation.model_copy(update={"status": "deleting"}))
        for document_id in conversation.document_ids:
            await self.remove_private_document(document_id, conversation.conversation_id)
        self.chats.delete(conversation.conversation_id)

    def prune_missing_attachments(self) -> None:
        """Remove stale links after document deletion while retaining message snapshots."""
        for conversation in self.chats.all():
            existing_ids = [
                document_id
                for document_id in conversation.document_ids
                if self.registry.get(document_id) is not None
            ]
            if existing_ids != conversation.document_ids and conversation.status == "active":
                self.chats.save(conversation.model_copy(update={"document_ids": existing_ids}))

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
        for conversation in self.chats.all():
            if conversation.status == "deleting":
                try:
                    await self.delete_conversation(conversation)
                except AppError, OSError:
                    logger.warning("chat_cleanup_pending")
        self.prune_missing_attachments()


def get_services(request: Request) -> Services:
    """Resolve the application bundle through a replaceable FastAPI dependency."""
    services: Services = request.app.state.services
    return services

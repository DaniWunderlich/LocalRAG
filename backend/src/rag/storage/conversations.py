"""Atomic per-conversation storage on the existing persistent document volume."""

import logging
from pathlib import Path
from uuid import UUID

from rag.errors import AppError
from rag.models import Conversation, ConversationSummary
from rag.storage.documents import atomic_write

logger = logging.getLogger(__name__)


def unreadable_record(path: Path, error: Exception) -> AppError:
    """Identify the record for operators without logging saved conversation contents."""
    logger.warning(
        "conversation_record_unreadable",
        extra={"record_name": path.name, "error_type": type(error).__name__},
    )
    return AppError(
        "A saved chat record is unreadable. Restore or repair it before opening it or removing private files.",
        409,
        "chat_record_unreadable",
    )


class ConversationStore:
    """Keep independent JSON records; the application lock serialises all writes."""

    def __init__(self, storage_path: Path) -> None:
        self.path = storage_path / "chats"
        self.path.mkdir(parents=True, exist_ok=True)

    def get(self, conversation_id: UUID) -> Conversation | None:
        """Load a complete conversation without trusting a user-controlled path."""
        path = self.path / f"{conversation_id}.json"
        if not path.exists():
            return None
        try:
            conversation = Conversation.model_validate_json(path.read_bytes())
            if conversation.conversation_id != conversation_id:
                raise ValueError("Conversation file ID is inconsistent.")
            return conversation
        except (ValueError, OSError) as error:
            raise unreadable_record(path, error) from error

    def all(self, *, strict: bool = True) -> list[Conversation]:
        """Allow partial navigation while requiring complete references before cleanup."""
        conversations = []
        for path in self.path.glob("*.json"):
            try:
                try:
                    conversation_id = UUID(path.stem)
                    if path.name != f"{conversation_id}.json":
                        raise ValueError("Conversation filename is not canonical.")
                except ValueError as error:
                    raise unreadable_record(path, error) from error
                conversation = self.get(conversation_id)
            except AppError:
                if strict:
                    raise
                continue
            if conversation is not None:
                conversations.append(conversation)
        return sorted(conversations, key=lambda item: item.updated_at, reverse=True)

    def summaries(self) -> list[ConversationSummary]:
        """Expose navigation data without sending stored excerpts to the frontend."""
        return [
            ConversationSummary(
                conversation_id=item.conversation_id,
                title=item.title,
                folder=item.folder,
                updated_at=item.updated_at,
                message_count=len(item.messages),
                document_count=len(item.document_ids),
                status=item.status,
            )
            for item in self.all(strict=False)
        ]

    def save(self, conversation: Conversation) -> None:
        """Commit both sides of a successful exchange in one atomic replacement."""
        atomic_write(
            self.path / f"{conversation.conversation_id}.json",
            conversation.model_dump_json(indent=2).encode("utf-8"),
        )

    def delete(self, conversation_id: UUID) -> None:
        """Remove a transcript after private attachment cleanup has succeeded."""
        (self.path / f"{conversation_id}.json").unlink(missing_ok=True)

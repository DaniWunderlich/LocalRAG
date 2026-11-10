"""Durable conversations, isolated evidence and idempotent follow-up messages."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Response, UploadFile

from rag.errors import AppError
from rag.generation.generator import generate_answer
from rag.ingestion.indexer import index_document
from rag.ingestion.loader import load_document
from rag.models import (
    Conversation,
    ConversationCreate,
    ConversationImport,
    ConversationMessage,
    ConversationSend,
    ConversationSummary,
    ConversationUpdate,
    DocumentMeta,
    HistoryMessage,
)
from rag.retrieval.retriever import retrieve_chunks
from rag.services import Services, get_services

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])
Bundle = Annotated[Services, Depends(get_services)]


def require_conversation(conversation_id: UUID, services: Services) -> Conversation:
    """Return a saved conversation or an explicit missing-record error."""
    conversation = services.chats.get(conversation_id)
    if conversation is None:
        raise AppError("Chat not found.", 404, "chat_not_found")
    return conversation


def require_active(conversation_id: UUID, services: Services) -> Conversation:
    """Prevent edits from reviving an interrupted deletion."""
    conversation = require_conversation(conversation_id, services)
    if conversation.status != "active":
        raise AppError("Chat deletion is pending. Retry deleting it.", 409, "chat_deleting")
    return conversation


@router.get("")
async def list_conversations(services: Bundle) -> list[ConversationSummary]:
    """Return independently selectable conversations in recent-activity order."""
    return services.chats.summaries()


@router.post("", status_code=201)
async def create_conversation(request: ConversationCreate, services: Bundle) -> Conversation:
    """Create a durable empty thread with private evidence by default."""
    async with services.lock:
        now = datetime.now(UTC)
        conversation = Conversation(
            conversation_id=uuid4(),
            created_at=now,
            updated_at=now,
            model=request.model or services.settings.ollama_chat_model,
            top_k=request.top_k or services.settings.rag_top_k,
            temperature=services.settings.rag_temperature
            if request.temperature is None
            else request.temperature,
        )
        services.chats.save(conversation)
        return conversation


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: UUID, services: Bundle) -> Conversation:
    """Restore the exact transcript, evidence snapshots and thread preferences."""
    return require_conversation(conversation_id, services)


@router.post("/import", status_code=201)
async def import_conversation(request: ConversationImport, services: Bundle) -> Conversation:
    """Preserve the original session transcript without sending it back to an LLM."""
    async with services.lock:
        existing = services.chats.get(request.conversation_id)
        if existing is not None:
            return existing
        now = datetime.now(UTC)
        first_question = next(
            (item.content for item in request.messages if item.role == "user"), "Imported chat"
        )
        conversation = Conversation(
            conversation_id=request.conversation_id,
            title=first_question[:70],
            created_at=now,
            updated_at=now,
            model=request.model,
            top_k=request.top_k or services.settings.rag_top_k,
            temperature=services.settings.rag_temperature
            if request.temperature is None
            else request.temperature,
            use_library=True,
            messages=[
                ConversationMessage(
                    message_id=uuid4(),
                    created_at=now,
                    role=item.role,
                    content=item.content,
                    sources=item.sources,
                )
                for item in request.messages
            ],
        )
        services.chats.save(conversation)
        return conversation


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: UUID,
    request: ConversationUpdate,
    services: Bundle,
) -> Conversation:
    """Rename a thread or change only its explicitly supplied preferences."""
    async with services.lock:
        conversation = require_active(conversation_id, services)
        updated = conversation.model_copy(
            update={
                **request.model_dump(exclude_none=True),
                "updated_at": datetime.now(UTC),
                "automatic_title": False
                if request.title is not None
                else conversation.automatic_title,
            }
        )
        services.chats.save(updated)
        return updated


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: UUID, services: Bundle) -> Response:
    """Delete one chat and unshared private originals, preserving shared evidence."""
    async with services.lock:
        conversation = require_conversation(conversation_id, services)
        await services.delete_conversation(conversation)
    return Response(status_code=204)


@router.get("/{conversation_id}/documents")
async def list_attachments(conversation_id: UUID, services: Bundle) -> list[DocumentMeta]:
    """Return this thread's attachments, including failed uploads for retry."""
    conversation = require_conversation(conversation_id, services)
    return [
        meta
        for document_id in conversation.document_ids
        if (meta := services.registry.get(document_id)) is not None
    ]


@router.post("/{conversation_id}/documents", status_code=201)
async def upload_attachment(
    conversation_id: UUID,
    services: Bundle,
    file: Annotated[UploadFile, File()],
) -> DocumentMeta:
    """Index a private attachment, reusing identical content without leaking scope."""
    try:
        async with services.lock:
            conversation = require_active(conversation_id, services)
            before = {meta.document_id for meta in services.registry.list()}
            meta = await load_document(file, services.registry, services.settings, in_library=False)
            if meta.document_id not in conversation.document_ids:
                conversation = conversation.model_copy(
                    update={
                        "document_ids": [*conversation.document_ids, meta.document_id],
                        "title": meta.filename[:100]
                        if conversation.automatic_title and not conversation.messages
                        else conversation.title,
                        "updated_at": datetime.now(UTC),
                    }
                )
                try:
                    services.chats.save(conversation)
                except OSError:
                    if meta.document_id not in before:
                        services.registry.file_path(meta.document_id).unlink(missing_ok=True)
                        services.registry.delete(meta.document_id)
                    raise
            if meta.status == "indexed":
                return meta
            return await index_document(
                meta,
                services.registry,
                services.ollama,
                services.qdrant,
                services.settings,
            )
    finally:
        await file.close()


@router.delete("/{conversation_id}/documents/{document_id}", status_code=204)
async def detach_document(conversation_id: UUID, document_id: UUID, services: Bundle) -> Response:
    """Detach evidence; remove its original only when no library or other chat uses it."""
    async with services.lock:
        conversation = require_active(conversation_id, services)
        if document_id not in conversation.document_ids:
            raise AppError("Attachment not found.", 404, "attachment_not_found")
        await services.remove_private_document(document_id, conversation_id)
        services.chats.save(
            conversation.model_copy(
                update={
                    "document_ids": [
                        item for item in conversation.document_ids if item != document_id
                    ],
                    "updated_at": datetime.now(UTC),
                }
            )
        )
    return Response(status_code=204)


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID,
    request: ConversationSend,
    services: Bundle,
) -> Conversation:
    """Ground a follow-up in this thread's evidence and commit the exchange atomically."""
    async with services.lock:
        conversation = require_active(conversation_id, services)
        previous = next(
            (item for item in conversation.messages if item.message_id == request.request_id), None
        )
        if previous is not None:
            if previous.role != "user" or previous.content != request.message:
                raise AppError(
                    "This request ID belongs to another message.", 409, "request_conflict"
                )
            return conversation
        if not conversation.model:
            raise AppError("Choose a local chat model first.", 422, "model_required")
        document_ids = set(conversation.document_ids)
        if conversation.use_library:
            document_ids.update(
                meta.document_id for meta in services.registry.list() if meta.in_library
            )
        last_questions = [item.content for item in conversation.messages if item.role == "user"][
            -2:
        ]
        query = ("\n".join([*last_questions, request.message]))[-8000:]
        sources = await retrieve_chunks(
            query,
            conversation.top_k,
            services.ollama,
            services.qdrant,
            services.registry,
            services.settings,
            document_ids=document_ids,
        )
        history = [
            HistoryMessage(role=item.role, content=item.content)
            for item in conversation.messages[-12:]
        ]
        result = await generate_answer(
            request.message,
            sources,
            conversation.model,
            conversation.temperature,
            services.ollama,
            services.settings,
            history=history,
        )
        now = datetime.now(UTC)
        turns = [
            ConversationMessage(
                message_id=request.request_id, role="user", content=request.message, created_at=now
            ),
            ConversationMessage(
                message_id=uuid4(),
                role="assistant",
                content=result.answer,
                sources=result.sources,
                created_at=now,
            ),
        ]
        conversation = conversation.model_copy(
            update={
                "messages": [*conversation.messages, *turns],
                "title": request.message[:70]
                if conversation.automatic_title and not conversation.messages
                else conversation.title,
                "updated_at": now,
            }
        )
        services.chats.save(conversation)
        return conversation

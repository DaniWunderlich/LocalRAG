"""Typed document, retrieval and API data shared by the application modules."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentMeta(BaseModel):
    """Persistent metadata independent of the vector index."""

    model_config = ConfigDict(frozen=True)
    document_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_at: datetime
    chunk_count: int = 0
    status: Literal["processing", "indexed", "failed", "deleting"] = "processing"
    error: str | None = None
    in_library: bool = True


class PageContent(BaseModel):
    """Extracted text retaining its original page or section."""

    page: int | None = None
    section: str | None = None
    text: str


class Chunk(PageContent):
    """A bounded piece of text with its document-wide position."""

    chunk_index: int
    token_count: int


class Source(PageContent):
    """A retrieved excerpt; source IDs refer to the exact generation context."""

    source_id: int = 0
    chunk_id: str
    document_id: UUID
    filename: str
    chunk_index: int
    score: float
    embedding_model: str


class SearchRequest(BaseModel):
    """Bound the query and retrieval workload."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: str = Field(min_length=1, max_length=8000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class ChatRequest(BaseModel):
    """A stateless question with optional session-specific settings."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    message: str = Field(min_length=1, max_length=8000)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    top_k: int | None = Field(default=None, ge=1, le=20)
    temperature: float | None = Field(default=None, ge=0, le=1)


class ChatResponse(BaseModel):
    """Generated answer and precisely the excerpts supplied to the model."""

    answer: str
    sources: list[Source]


class HistoryMessage(BaseModel):
    """A previous turn used to interpret a follow-up, without becoming evidence."""

    role: Literal["user", "assistant"]
    content: str


class ConversationMessage(HistoryMessage):
    """A durable message and its original evidence snapshot."""

    message_id: UUID
    created_at: datetime
    sources: list[Source] = Field(default_factory=list)


class Conversation(BaseModel):
    """One independently configured, locally persisted conversation."""

    conversation_id: UUID
    title: str = "New chat"
    automatic_title: bool = True
    created_at: datetime
    updated_at: datetime
    model: str = ""
    top_k: int = Field(default=5, ge=1, le=20)
    temperature: float = Field(default=0.2, ge=0, le=1)
    use_library: bool = False
    document_ids: list[UUID] = Field(default_factory=list)
    messages: list[ConversationMessage] = Field(default_factory=list)
    status: Literal["active", "deleting"] = "active"


class ConversationSummary(BaseModel):
    """Lightweight navigation data without loading messages into the browser."""

    conversation_id: UUID
    title: str
    updated_at: datetime
    message_count: int
    document_count: int
    status: Literal["active", "deleting"]


class ConversationCreate(BaseModel):
    """Optional initial model, otherwise using the backend default."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    model: str = Field(default="", max_length=200)
    top_k: int | None = Field(default=None, ge=1, le=20)
    temperature: float | None = Field(default=None, ge=0, le=1)


class ConversationUpdate(BaseModel):
    """Validated partial edits to a conversation's title and preferences."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=120)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    top_k: int | None = Field(default=None, ge=1, le=20)
    temperature: float | None = Field(default=None, ge=0, le=1)
    use_library: bool | None = None


class ConversationSend(BaseModel):
    """Idempotent submission of a question to one conversation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    request_id: UUID
    message: str = Field(min_length=1, max_length=8000)


class ImportedMessage(HistoryMessage):
    """A message from the original session-only frontend."""

    content: str = Field(max_length=200000)
    sources: list[Source] = Field(default_factory=list, max_length=20)


class ConversationImport(ConversationCreate):
    """Idempotently preserve a pre-upgrade browser transcript."""

    conversation_id: UUID
    messages: list[ImportedMessage] = Field(min_length=1, max_length=1000)

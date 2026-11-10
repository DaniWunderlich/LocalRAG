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

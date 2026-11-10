"""Validated environment configuration for the single-instance application."""

from pathlib import Path

from pydantic import AnyHttpUrl, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load configuration once during application startup."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", str_strip_whitespace=True)

    ollama_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:11434")
    ollama_chat_model: str = ""
    ollama_embedding_model: str = Field(default="embeddinggemma:300m", min_length=1)
    ollama_timeout_seconds: float = Field(default=180, gt=0)
    qdrant_url: AnyHttpUrl = AnyHttpUrl("http://localhost:6333")
    qdrant_collection: str = Field(default="rag_documents", pattern=r"^[A-Za-z0-9_-]+$")
    rag_chunk_size: int = Field(default=600, ge=16, le=8192)
    rag_chunk_overlap: int = Field(default=80, ge=0)
    rag_top_k: int = Field(default=5, ge=1, le=20)
    rag_temperature: float = Field(default=0.2, ge=0, le=1)
    rag_context_tokens: int = Field(default=4096, ge=128, le=131072)
    rag_answer_tokens: int = Field(default=1024, ge=64, le=32768)
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    document_storage_path: Path = Path("data/documents")

    @model_validator(mode="after")
    def validate_overlap(self) -> Settings:
        """Reject chunk configurations that cannot make progress."""
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE.")
        return self

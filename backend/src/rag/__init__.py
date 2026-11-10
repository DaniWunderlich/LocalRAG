"""
Local RAG backend package.

This package contains the entire RAG application:
  - api:        FastAPI routers (chat, documents, search, health)
  - ingestion:  Document loading, parsing, chunking, and indexing
  - retrieval:  Qdrant similarity search and context assembly
  - generation: Prompt construction and Ollama answer generation
  - providers:  Low-level HTTP clients for Ollama and Qdrant
  - storage:    JSON-based document registry
  - config:     Application settings loaded from environment variables
"""

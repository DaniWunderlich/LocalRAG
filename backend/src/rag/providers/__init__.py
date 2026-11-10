"""
Providers sub-package.

Low-level HTTP clients for external services:
  ollama  – Ollama REST API (embeddings and chat completions)
  qdrant  – Qdrant vector database (collection management, upsert, search, delete)

All higher-level modules (indexer, retriever, generator) depend on these
interfaces, not on concrete implementations.  This makes the providers
easy to replace with test doubles during unit testing.
"""

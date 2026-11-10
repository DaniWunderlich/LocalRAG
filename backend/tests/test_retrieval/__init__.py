"""
Unit tests for the retrieval pipeline.

Planned test cases:

  test_retriever.py
    - retrieve_chunks() calls OllamaClient.embed() with the query text.
    - retrieve_chunks() calls QdrantProvider.search() with the query vector.
    - Returned RetrievedChunk objects have the correct fields populated.
    - top_k is passed through correctly.
    - Empty Qdrant result returns an empty list (no exception).
    - Ollama connection failure raises OllamaConnectionError.
    - Qdrant connection failure raises QdrantConnectionError.
    - assemble_context() respects the token budget (no overflow).
    - assemble_context() includes source labels ([Source 1], [Source 2], ...).
    - assemble_context() with an empty chunk list returns an empty string.
"""

"""
Test suite for the Local RAG backend.

Test organisation:
  test_ingestion/   – Unit tests for loader, parser, chunker, indexer.
  test_retrieval/   – Unit tests for the retriever.
  test_generation/  – Unit tests for the generator.

Integration tests (requiring live Qdrant and Ollama) are tagged with
pytest.mark.integration and are excluded from the default test run.

Run unit tests only:
  pytest

Run all tests including integration:
  pytest -m ""
"""

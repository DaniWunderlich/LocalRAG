"""
Unit tests for the ingestion pipeline.

Planned test cases:

  test_loader.py
    - Accepted file types are stored without error.
    - Oversized files raise FileTooLargeError.
    - Unsupported MIME types raise UnsupportedFileTypeError.
    - Uploading the same file twice raises DuplicateDocumentError.
    - SHA-256 hash in the registry matches the uploaded file.
    - Stored filename uses the document_id, not the original name.

  test_parser.py
    - PDF extraction returns non-empty PageContent list.
    - DOCX extraction returns non-empty PageContent list.
    - TXT extraction returns a single PageContent item.
    - Markdown extraction returns raw text.
    - Scanned PDF (no text layer) raises ExtractionError.
    - Empty file raises ExtractionError.

  test_chunker.py
    - No chunk exceeds RAG_CHUNK_SIZE tokens.
    - Overlap is applied between consecutive chunks.
    - chunk_index values are sequential and start from 0.
    - Page metadata is propagated to chunks.
    - Single short page yields exactly one chunk.

  test_indexer.py
    - Successful indexing updates registry status to "indexed".
    - Embedding failure sets status to "failed" and cleans up Qdrant.
    - Qdrant upsert failure sets status to "failed".
    - Embedding model mismatch raises EmbeddingModelMismatchError.
"""

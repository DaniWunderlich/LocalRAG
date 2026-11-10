"""
Ingestion sub-package.

The ingestion pipeline transforms an uploaded file into indexed vectors
stored in Qdrant.  The four modules cover distinct stages:

  loader   – Accepts the raw upload, validates it, computes its hash,
             persists the original file, and registers it.
  parser   – Extracts plain text from the stored file based on its type.
  chunker  – Splits extracted text into overlapping, token-aware chunks.
  indexer  – Orchestrates the full pipeline and writes vectors to Qdrant.
"""

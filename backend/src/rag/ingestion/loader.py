"""Bounded upload validation, hashing and UUID-based original storage."""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import UploadFile

from rag.config import Settings
from rag.errors import AppError
from rag.models import DocumentMeta
from rag.storage.documents import DocumentRegistry, atomic_write

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}


async def load_document(
    file: UploadFile,
    registry: DocumentRegistry,
    settings: Settings,
) -> DocumentMeta:
    """Validate before writing; retry failed hashes using the existing document ID."""
    filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    extension = "." + filename.rsplit(".", 1)[-1].lower()
    content_type = CONTENT_TYPES.get(extension)
    supplied_type = (file.content_type or "").split(";", 1)[0].lower()
    allowed = {content_type, "", "application/octet-stream"}
    if content_type == "text/markdown":
        allowed.add("text/plain")
        allowed.add("text/x-markdown")
    if content_type is None or supplied_type not in allowed:
        raise AppError(
            "Supported formats are PDF, DOCX, UTF-8 TXT and Markdown.", 415, "unsupported_file"
        )
    data = bytearray()
    while block := await file.read(64 * 1024):
        data.extend(block)
        if len(data) > settings.max_upload_bytes:
            raise AppError("The document exceeds the upload size limit.", 413, "file_too_large")
    if not data:
        raise AppError("The document is empty.", 422, "empty_document")
    if content_type == "application/pdf" and not data.startswith(b"%PDF-"):
        raise AppError("The file is not a valid PDF.", 422, "invalid_document")
    if content_type.endswith("wordprocessingml.document") and not data.startswith(b"PK"):
        raise AppError("The file is not a valid DOCX.", 422, "invalid_document")
    if content_type.startswith("text/"):
        try:
            text = data.decode("utf-8-sig")
            if any(ord(char) < 32 and char not in "\n\r\t\f" for char in text):
                raise ValueError("Binary control character.")
        except (UnicodeDecodeError, ValueError) as exc:
            raise AppError(
                "Text documents must contain valid UTF-8 text.", 422, "invalid_document"
            ) from exc
    digest = hashlib.sha256(data).hexdigest()
    existing = registry.find_by_hash(digest)
    if existing is not None and existing.status != "failed":
        raise AppError(
            f"This document already exists ({existing.document_id}).",
            409,
            "duplicate_document",
        )
    meta = DocumentMeta(
        document_id=existing.document_id if existing else uuid4(),
        filename=filename[:255],
        content_type=content_type,
        size_bytes=len(data),
        sha256=digest,
        uploaded_at=existing.uploaded_at if existing else datetime.now(UTC),
    )
    registry.save(meta)
    try:
        atomic_write(registry.file_path(meta.document_id), bytes(data))
    except OSError as exc:
        registry.save(
            meta.model_copy(
                update={"status": "failed", "error": "Original file could not be saved."}
            )
        )
        raise AppError("Original file could not be saved.", 503, "storage_unavailable") from exc
    return meta

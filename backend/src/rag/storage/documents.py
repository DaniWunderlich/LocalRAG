"""Atomic JSON metadata and original-file storage for one backend process."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID

from pydantic import TypeAdapter

from rag.models import DocumentMeta


def atomic_write(path: Path, content: bytes) -> None:
    """Flush a sibling temporary file before replacing its destination."""
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class DocumentRegistry:
    """Keep durable metadata; callers serialise complete mutations with a lock."""

    def __init__(self, storage_path: Path, registry_filename: str = "registry.json") -> None:
        self.path = storage_path
        self.path.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.path / registry_filename
        if not self.registry_path.exists():
            atomic_write(self.registry_path, b"{}")
        self._documents = TypeAdapter(dict[UUID, DocumentMeta]).validate_json(
            self.registry_path.read_bytes()
        )
        if any(key != value.document_id for key, value in self._documents.items()):
            raise ValueError("Document registry IDs are inconsistent.")

    def file_path(self, document_id: UUID) -> Path:
        """Resolve an internal UUID, never a user-supplied filename."""
        return self.path / str(document_id)

    def get(self, document_id: UUID) -> DocumentMeta | None:
        """Find one document, including failed and interrupted uploads."""
        return self._documents.get(document_id)

    def list(self) -> list[DocumentMeta]:
        """Return newest uploads first."""
        return sorted(self._documents.values(), key=lambda item: item.uploaded_at, reverse=True)

    def find_by_hash(self, sha256: str) -> DocumentMeta | None:
        """Find an identical original independently of its indexing status."""
        return next((item for item in self._documents.values() if item.sha256 == sha256), None)

    def save(self, meta: DocumentMeta) -> None:
        """Commit a complete record without changing memory if persistence fails."""
        self._commit(self._documents | {meta.document_id: meta})

    def delete(self, document_id: UUID) -> None:
        """Remove metadata only after the original and vectors have been removed."""
        documents = self._documents.copy()
        documents.pop(document_id, None)
        self._commit(documents)

    def _commit(self, documents: dict[UUID, DocumentMeta]) -> None:
        content = {str(key): value.model_dump(mode="json") for key, value in documents.items()}
        atomic_write(self.registry_path, json.dumps(content, indent=2).encode("utf-8"))
        self._documents = documents

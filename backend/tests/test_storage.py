"""Durable registry replacement, corruption handling and reindex staging."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from rag.config import Settings
from rag.errors import AppError
from rag.models import DocumentMeta
from rag.reindex import rebuild
from rag.storage.documents import DocumentRegistry


def record() -> DocumentMeta:
    """Create a small metadata fixture independent of any external service."""
    return DocumentMeta(
        document_id=uuid4(),
        filename="original.txt",
        content_type="text/plain",
        size_bytes=6,
        sha256="synthetic-hash",
        uploaded_at=datetime.now(UTC),
        status="indexed",
    )


def test_failed_atomic_replace_preserves_previous_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = DocumentRegistry(tmp_path)
    meta = record()
    registry.save(meta)
    original = registry.registry_path.read_bytes()

    def fail_replace(source: object, destination: object) -> None:
        raise OSError("Simulated storage failure.")

    monkeypatch.setattr("rag.storage.documents.os.replace", fail_replace)
    with pytest.raises(OSError):
        registry.delete(meta.document_id)
    assert registry.get(meta.document_id) == meta
    assert registry.registry_path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [registry.registry_path]


def test_corrupt_registry_is_not_silently_discarded(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError):
        DocumentRegistry(tmp_path)
    assert path.read_text(encoding="utf-8") == "{broken"


async def test_reindex_failure_preserves_active_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = DocumentRegistry(tmp_path)
    registry.save(record())
    original = registry.registry_path.read_bytes()
    qdrant = AsyncMock()
    qdrant.exists.return_value = False
    ollama = AsyncMock()
    monkeypatch.setattr("rag.reindex.QdrantProvider", lambda *args: qdrant)
    monkeypatch.setattr("rag.reindex.OllamaClient", lambda *args: ollama)
    monkeypatch.setattr("rag.reindex.index_document", AsyncMock(side_effect=AppError("Failed.")))
    settings = Settings(_env_file=None, document_storage_path=tmp_path)
    with pytest.raises(AppError):
        await rebuild(settings, "new_index", "new:model")
    assert registry.registry_path.read_bytes() == original
    assert not (tmp_path / "registry.reindex.json").exists()


async def test_reindex_refuses_the_active_collection(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, document_storage_path=tmp_path)
    with pytest.raises(AppError, match="new collection"):
        await rebuild(settings, settings.qdrant_collection, "new:model")


async def test_successful_reindex_commits_staged_metadata_and_keeps_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = DocumentRegistry(tmp_path)
    meta = record().model_copy(update={"status": "failed", "error": "Previous failure."})
    registry.save(meta)
    original = registry.registry_path.read_bytes()
    qdrant = AsyncMock()
    qdrant.exists.return_value = False
    monkeypatch.setattr("rag.reindex.QdrantProvider", lambda *args: qdrant)
    monkeypatch.setattr("rag.reindex.OllamaClient", lambda *args: AsyncMock())

    async def successful_index(
        document: DocumentMeta,
        staged: DocumentRegistry,
        *args: object,
    ) -> DocumentMeta:
        result = document.model_copy(update={"status": "indexed", "chunk_count": 2})
        staged.save(result)
        return result

    monkeypatch.setattr("rag.reindex.index_document", successful_index)
    settings = Settings(_env_file=None, document_storage_path=tmp_path)
    assert await rebuild(settings, "new_index", "new:model") == 1
    restored = DocumentRegistry(tmp_path).get(meta.document_id)
    assert restored is not None and restored.status == "indexed" and restored.chunk_count == 2
    backups = list(tmp_path.glob("registry.before-reindex-*.json"))
    assert len(backups) == 1 and backups[0].read_bytes() == original
    assert not (tmp_path / "registry.reindex.json").exists()

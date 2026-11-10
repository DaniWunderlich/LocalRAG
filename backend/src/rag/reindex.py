"""Offline, staged reindexing into a fresh collection while the backend is stopped."""

import argparse
import asyncio
from datetime import UTC, datetime

from rag.config import Settings
from rag.errors import AppError
from rag.ingestion.indexer import index_document
from rag.providers.ollama import OllamaClient
from rag.providers.qdrant import QdrantProvider
from rag.storage.documents import DocumentRegistry, atomic_write


async def rebuild(settings: Settings, target_collection: str, embedding_model: str) -> int:
    """Retain the old collection and commit staged metadata only after full success."""
    if target_collection == settings.qdrant_collection:
        raise AppError(
            "Choose a new collection name; the active collection must be preserved.", 422
        )
    target = Settings.model_validate(
        settings.model_dump()
        | {
            "qdrant_collection": target_collection,
            "ollama_embedding_model": embedding_model,
        }
    )
    registry = DocumentRegistry(settings.document_storage_path)
    ollama = OllamaClient(str(settings.ollama_base_url), settings.ollama_timeout_seconds)
    qdrant = QdrantProvider(str(settings.qdrant_url), target_collection)
    staging_path = registry.path / "registry.reindex.json"
    try:
        if await qdrant.exists():
            raise AppError("The target collection already exists. Choose a fresh name.", 409)
        documents = registry.list()
        if any(meta.status == "deleting" for meta in documents):
            raise AppError("Complete pending document deletions before rebuilding the index.", 409)
        if not documents:
            raise AppError("There are no documents to reindex.", 422)
        atomic_write(staging_path, b"{}")
        staged = DocumentRegistry(registry.path, staging_path.name)
        for meta in documents:
            processing = meta.model_copy(
                update={"status": "processing", "chunk_count": 0, "error": None}
            )
            staged.save(processing)
            await index_document(processing, staged, ollama, qdrant, target)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup = registry.path / f"registry.before-reindex-{timestamp}.json"
        atomic_write(backup, registry.registry_path.read_bytes())
        atomic_write(registry.registry_path, staging_path.read_bytes())
        print(f"Reindexed {len(documents)} documents. Previous registry saved as {backup.name}.")
        print(
            f"Set QDRANT_COLLECTION={target_collection} and OLLAMA_EMBEDDING_MODEL={embedding_model} before restarting."
        )
        return len(documents)
    finally:
        staging_path.unlink(missing_ok=True)
        await ollama.close()
        await qdrant.close()


def main() -> None:
    """Require explicit target settings and an operator-controlled maintenance window."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-collection", required=True)
    parser.add_argument("--embedding-model", required=True)
    args = parser.parse_args()
    try:
        asyncio.run(rebuild(Settings(), args.target_collection, args.embedding_model))
    except AppError as exc:
        parser.exit(1, f"{exc.message}\nThe previous registry and collection remain available.\n")


if __name__ == "__main__":
    main()

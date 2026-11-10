"""Document upload, inspection and deletion through the ingestion pipeline."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Response, UploadFile

from rag.errors import AppError
from rag.ingestion.indexer import index_document
from rag.ingestion.loader import load_document
from rag.models import DocumentMeta
from rag.services import Services, get_services

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
Bundle = Annotated[Services, Depends(get_services)]
logger = logging.getLogger(__name__)


@router.post("", response_model=DocumentMeta, status_code=201)
async def upload_document(services: Bundle, file: Annotated[UploadFile, File()]) -> DocumentMeta:
    """Index synchronously; identical failed uploads retry their existing record."""
    try:
        async with services.lock:
            meta = await load_document(file, services.registry, services.settings)
            logger.info(
                "document_uploaded",
                extra={"document_id": str(meta.document_id), "size_bytes": meta.size_bytes},
            )
            return await index_document(
                meta,
                services.registry,
                services.ollama,
                services.qdrant,
                services.settings,
            )
    finally:
        await file.close()


@router.get("", response_model=list[DocumentMeta])
async def list_documents(services: Bundle) -> list[DocumentMeta]:
    """Include failed documents so that users can retry or remove them."""
    return services.registry.list()


@router.get("/{document_id}", response_model=DocumentMeta)
async def get_document(document_id: UUID, services: Bundle) -> DocumentMeta:
    """Look up a document without depending on the vector database."""
    meta = services.registry.get(document_id)
    if meta is None:
        raise AppError("Document not found.", 404, "document_not_found")
    return meta


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: UUID, services: Bundle) -> Response:
    """Hide the document, remove vectors and original, then remove its metadata."""
    async with services.lock:
        meta = await get_document(document_id, services)
        services.registry.save(meta.model_copy(update={"status": "deleting"}))
        await services.qdrant.delete_document(document_id)
        services.registry.file_path(document_id).unlink(missing_ok=True)
        services.registry.delete(document_id)
        logger.info("document_deleted", extra={"document_id": str(document_id)})
    return Response(status_code=204)

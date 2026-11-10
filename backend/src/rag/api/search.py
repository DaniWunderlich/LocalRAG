"""Retrieval endpoint independent of answer generation."""

from typing import Annotated

from fastapi import APIRouter, Depends

from rag.models import SearchRequest, Source
from rag.retrieval.retriever import retrieve_chunks
from rag.services import Services, get_services

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.post("/search", response_model=list[Source])
async def search(
    request: SearchRequest, services: Annotated[Services, Depends(get_services)]
) -> list[Source]:
    """Return ranked excerpts and scores for inspection and evaluation."""
    async with services.lock:
        return await retrieve_chunks(
            request.query,
            request.top_k or services.settings.rag_top_k,
            services.ollama,
            services.qdrant,
            services.registry,
            services.settings,
        )

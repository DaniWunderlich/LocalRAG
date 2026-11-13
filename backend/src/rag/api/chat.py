"""Stateless retrieval and generation endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends

from rag.errors import AppError
from rag.generation.generator import generate_answer
from rag.models import ChatRequest, ChatResponse
from rag.retrieval.retriever import retrieve_chunks
from rag.services import Services, get_services

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest, services: Annotated[Services, Depends(get_services)]
) -> ChatResponse:
    """Answer with an explicitly selected or configured local completion model."""
    settings = services.settings
    model = request.model or settings.ollama_chat_model
    if not model:
        raise AppError(
            "Select an installed chat model before asking a question.", 422, "model_required"
        )
    async with services.lock:
        has_documents = any(meta.in_library for meta in services.registry.list())
        sources = await retrieve_chunks(
            request.message,
            request.top_k or settings.rag_top_k,
            services.ollama,
            services.qdrant,
            services.registry,
            settings,
        )
    temperature = settings.rag_temperature if request.temperature is None else request.temperature
    return await generate_answer(
        request.message,
        sources,
        model,
        temperature,
        services.ollama,
        settings,
        allow_general=not has_documents,
    )

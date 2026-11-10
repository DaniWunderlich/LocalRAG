"""Separate process liveness, dependency readiness and model discovery."""

import asyncio
import os
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from rag.errors import AppError
from rag.services import Services, get_services

router = APIRouter(tags=["system"])
Bundle = Annotated[Services, Depends(get_services)]


@router.get("/health/live")
async def live() -> dict[str, str]:
    """Report process health without calling external dependencies."""
    return {"status": "alive"}


@router.get("/health/ready")
async def ready(services: Bundle) -> JSONResponse:
    """Check storage, both services and the configured embedding model."""
    ollama, qdrant = await asyncio.gather(services.ollama.ping(), services.qdrant.ping())
    embedding = False
    index = False
    if ollama:
        try:
            info = await services.ollama.model_info(
                services.settings.ollama_embedding_model, "embedding"
            )
            embedding = True
            if qdrant:
                exists = await services.qdrant.check_identity(info)
                index = exists or not any(
                    meta.status == "indexed" for meta in services.registry.list()
                )
        except AppError:
            pass
    storage = (
        services.registry.path.is_dir()
        and services.registry.registry_path.is_file()
        and os.access(services.registry.path, os.W_OK)
    )
    healthy = ollama and qdrant and embedding and index and storage
    return JSONResponse(
        {
            "status": "ready" if healthy else "not_ready",
            "checks": {
                "ollama": ollama,
                "qdrant": qdrant,
                "embedding_model": embedding,
                "index": index,
                "storage": storage,
            },
        },
        status_code=200 if healthy else 503,
    )


@router.get("/api/v1/models")
async def models(services: Bundle) -> dict[str, object]:
    """List only completion-capable local models and backend UI defaults."""
    return {
        "models": await services.ollama.list_models(),
        "default_model": services.settings.ollama_chat_model,
        "defaults": {
            "top_k": services.settings.rag_top_k,
            "temperature": services.settings.rag_temperature,
            "max_upload_bytes": services.settings.max_upload_bytes,
        },
    }

"""FastAPI application factory, client lifecycle and safe error responses."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from rag.api import chat, documents, health, search
from rag.config import Settings
from rag.errors import AppError
from rag.providers.ollama import OllamaClient
from rag.providers.qdrant import QdrantProvider
from rag.services import Services
from rag.storage.documents import DocumentRegistry


class JsonFormatter(logging.Formatter):
    """Emit structured records without exception bodies or document contents."""

    def format(self, record: logging.LogRecord) -> str:
        event: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key in (
            "document_id",
            "size_bytes",
            "chunk_count",
            "duration_ms",
            "result_count",
            "error_code",
            "error_type",
            "status_code",
            "cleanup_pending",
        ):
            if key in record.__dict__:
                event[key] = record.__dict__[key]
        return json.dumps(event)


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    """Create an isolated app; settings and service clients can be replaced in tests."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if services is None:
            config = settings or Settings()
            bundle = Services(
                config,
                DocumentRegistry(config.document_storage_path),
                OllamaClient(str(config.ollama_base_url), config.ollama_timeout_seconds),
                QdrantProvider(str(config.qdrant_url), config.qdrant_collection),
            )
        else:
            bundle = services
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger = logging.getLogger("rag")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        app.state.services = bundle
        try:
            await bundle.recover()
            yield
        finally:
            await bundle.ollama.close()
            await bundle.qdrant.close()
            logger.removeHandler(handler)

    app = FastAPI(title="Local RAG", version="0.1.0", lifespan=lifespan)
    for router in (documents.router, search.router, chat.router, health.router):
        app.include_router(router)

    @app.exception_handler(AppError)
    async def application_error(request: Request, error: AppError) -> JSONResponse:
        return JSONResponse(
            {"detail": error.message, "code": error.code},
            status_code=error.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "detail": "Invalid request. Check the fields and allowed ranges.",
                "code": "invalid_request",
            },
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        logging.getLogger("rag").error("request_failed", extra={"error_type": type(error).__name__})
        return JSONResponse(
            {
                "detail": "The operation failed. Check local storage and service availability.",
                "code": "internal_error",
            },
            status_code=500,
        )

    return app


app = create_app()

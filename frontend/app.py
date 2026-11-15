"""Serve the Gradio workspace and a lightweight container liveness endpoint."""

import os
import tempfile
from pathlib import Path
from typing import cast

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("GRADIO_TEMP_DIR", str(Path(tempfile.gettempdir()) / "localrag-uploads"))

import gradio as gr
from fastapi import FastAPI

from configuration import upload_limit
from ui import ROOT, create_workspace, reading_theme


def create_app() -> FastAPI:
    """Apply deployment limits when constructing an independent ASGI app."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health/live")
    def live() -> dict[str, str]:
        """Keep UI liveness independent of backend and model availability."""
        return {"status": "alive"}

    app = gr.mount_gradio_app(
        app,
        create_workspace(),
        path="/",
        server_port=7860,
        theme=reading_theme(),
        css_paths=ROOT / "styles.css",
        js=(ROOT / "workspace.js").read_text(encoding="utf-8"),
        footer_links=[],
        show_error=False,
        max_file_size=upload_limit(),
        ssr_mode=False,
        pwa=False,
        mcp_server=False,
        enable_monitoring=False,
    )

    return cast(FastAPI, app)


app = create_app()

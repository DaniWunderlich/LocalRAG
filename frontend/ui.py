"""Shared reading-desk styling, session preferences and evidence presentation."""

from pathlib import Path
from typing import Any

import streamlit as st

from api_client import BackendClient, BackendError


def apply_design() -> None:
    """Apply local, shared design tokens without remote fonts or scripts."""
    st.html(Path(__file__).with_name("styles.css"))


def format_file_size(size_bytes: int) -> str:
    """Keep small documents visibly distinct from empty files."""
    return f"{size_bytes} B" if size_bytes < 1024 else f"{size_bytes / 1024:.1f} KiB"


def initialise_preferences() -> list[str]:
    """Load backend defaults while preserving this browser's reading preferences."""
    data = BackendClient().models()
    defaults = data["defaults"]
    for key, value in {
        "top_k": defaults["top_k"],
        "temperature": defaults["temperature"],
        "show_sources": True,
        "max_upload_bytes": defaults["max_upload_bytes"],
    }.items():
        if key not in st.session_state:
            st.session_state[key] = value
    names: list[str] = data["models"]
    if st.session_state.get("selected_model") not in names:
        preferred = data.get("default_model")
        st.session_state.selected_model = (
            preferred if preferred in names else (names[0] if names else None)
        )
    return names


def show_sources(sources: list[dict[str, Any]]) -> None:
    """Keep source details beside the answer without competing with its prose."""
    if not sources:
        return
    with st.expander(f"Sources · {len(sources)}", icon=":material/library_books:"):
        for index, source in enumerate(sources, 1):
            label = f"[{source.get('source_id') or index}] {source['filename']}"
            if source.get("page"):
                label += f" · page {source['page']}"
            st.markdown(f"**{label}**")
            location = source.get("section") or f"Chunk {source['chunk_index'] + 1}"
            st.caption(f"{location} · similarity {source['score']:.3f}")
            if st.session_state.get("show_sources", True):
                st.text(source["text"])


def backend_notice() -> None:
    """Show failures explicitly; keep routine healthy status visually quiet."""
    try:
        status = BackendClient().request("GET", "/health/ready")
        if status["status"] == "ready":
            st.caption("Local services ready")
    except BackendError:
        st.warning("A local service is unavailable. Documents and saved chats remain local.")

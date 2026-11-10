"""Shared session preferences and source presentation."""

from typing import Any

import streamlit as st

from api_client import BackendClient, BackendError


def initialise_preferences() -> list[str]:
    """Initialise per-session choices from the backend's configured defaults."""
    data = BackendClient().models()
    defaults = data["defaults"]
    for key, value in {
        "top_k": defaults["top_k"],
        "temperature": defaults["temperature"],
        "show_sources": True,
        "messages": [],
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
    """Show each exact excerpt alongside its document, location and score."""
    for index, source in enumerate(sources, 1):
        label = f"Source {source.get('source_id') or index}: {source['filename']}"
        if source.get("page"):
            label += f" ? page {source['page']}"
        with st.expander(label):
            st.caption(f"Similarity: {source['score']:.3f} ? Chunk: {source['chunk_id']}")
            if source.get("section"):
                st.text(source["section"])
            if st.session_state.get("show_sources", True):
                st.text(source["text"])


def model_selector(names: list[str]) -> None:
    """Keep model selection separate from transient widget state across pages."""
    if not names:
        st.warning("No local chat models are available. Install one in Ollama first.")
        return
    selected = st.selectbox(
        "Chat model",
        names,
        index=names.index(st.session_state.selected_model),
    )
    st.session_state.selected_model = selected


def backend_notice() -> None:
    """Display the latest dependency status without blocking document management."""
    try:
        status = BackendClient().request("GET", "/health/ready")
        if status["status"] == "ready":
            st.caption("Local services are ready.")
    except BackendError:
        st.warning("A local service or the embedding model is unavailable. Check the backend logs.")

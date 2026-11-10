"""Session-only retrieval, generation and source display preferences."""

import streamlit as st

from api_client import BackendError
from ui import initialise_preferences, model_selector

st.set_page_config(page_title="Settings ? Local RAG", page_icon="??")
st.title("Settings")
st.caption("These preferences apply to this browser session.")

try:
    names = initialise_preferences()
except BackendError as error:
    st.error(str(error))
    st.stop()

model_selector(names)
st.session_state.top_k = st.number_input(
    "Maximum search results",
    min_value=1,
    max_value=20,
    value=int(st.session_state.top_k),
)
st.session_state.temperature = st.slider(
    "Temperature",
    min_value=0.0,
    max_value=1.0,
    value=float(st.session_state.temperature),
    step=0.05,
)
st.session_state.show_sources = st.checkbox(
    "Show source excerpts",
    value=bool(st.session_state.show_sources),
)
st.caption("The embedding model is managed by the backend to protect index compatibility.")

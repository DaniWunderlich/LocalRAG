"""Browser reading preferences and defaults for newly created conversations."""

import streamlit as st

from api_client import BackendError
from ui import backend_notice, initialise_preferences

st.title("Settings")
st.caption("Each saved chat keeps its own model, document scope and generation settings.")

st.subheader("Appearance")
st.caption(
    "Open the app menu at the top right to choose Light, Dark or System. "
    "Your browser remembers the choice across pages and reloads."
)

try:
    names = initialise_preferences()
except BackendError as error:
    st.error(str(error))
    st.stop()

st.subheader("Reading")
st.session_state.show_sources = st.checkbox(
    "Show source excerpts",
    value=bool(st.session_state.show_sources),
    help="Source references remain visible when excerpt text is hidden.",
)
st.subheader("New chat defaults")
if names:
    st.session_state.selected_model = st.selectbox(
        "Chat model",
        names,
        index=names.index(st.session_state.selected_model),
    )
with st.expander("Retrieval and generation"):
    st.session_state.top_k = st.number_input(
        "Maximum source excerpts",
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
st.caption("These defaults and reading preferences apply to this browser session.")
st.divider()
backend_notice()
st.caption("The embedding model is managed by the backend to keep the document index compatible.")

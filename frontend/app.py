"""Local RAG chat and retrieval inspection."""

import streamlit as st

from api_client import BackendClient, BackendError
from ui import backend_notice, initialise_preferences, model_selector, show_sources

st.set_page_config(page_title="Local RAG", page_icon="??", layout="wide")
st.title("Ask your documents")
st.caption("Upload documents on the Documents page, then ask a question and inspect its sources.")

try:
    names = initialise_preferences()
except BackendError as error:
    st.error(str(error))
    st.stop()

with st.sidebar:
    model_selector(names)
    backend_notice()
    if st.button("Clear conversation"):
        st.session_state.messages = []
        st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        show_sources(message.get("sources", []))

if question := st.chat_input("Ask a question about your documents", disabled=not names):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    try:
        with st.spinner("Searching documents and preparing an answer?"):
            result = BackendClient().chat(
                question,
                st.session_state.selected_model,
                st.session_state.top_k,
                st.session_state.temperature,
            )
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": result["answer"],
                "sources": result["sources"],
            }
        )
        with st.chat_message("assistant"):
            st.markdown(result["answer"])
            show_sources(result["sources"])
    except BackendError as error:
        st.error(str(error))

with st.expander("Inspect document search"):
    with st.form("search"):
        query = st.text_input("Search query")
        submitted = st.form_submit_button("Find excerpts")
    if submitted and query.strip():
        try:
            with st.spinner("Searching?"):
                sources = BackendClient().search(query, st.session_state.top_k)
            if sources:
                show_sources(sources)
            else:
                st.info("No indexed excerpts were found.")
        except BackendError as error:
            st.error(str(error))

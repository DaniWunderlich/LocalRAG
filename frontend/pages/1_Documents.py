"""A compact shared library, distinct from private conversation attachments."""

import streamlit as st

from api_client import BackendClient, BackendError
from ui import format_file_size, show_sources

st.title("Document library")
st.caption(
    "Documents here can be included in any chat. Chat attachments stay with their conversation."
)
client = BackendClient()

with st.expander("Add documents", icon=":material/add:"):
    with st.form("library-upload", clear_on_submit=True):
        files = st.file_uploader(
            "Choose documents",
            type=["pdf", "docx", "txt", "md", "markdown"],
            accept_multiple_files=True,
        )
        submitted = st.form_submit_button("Add to library")
    if submitted and files:
        for file in files:
            try:
                with st.spinner(f"Indexing {file.name}..."):
                    document = client.upload(file.name, file.getvalue(), file.type)
                st.success(f"{document['filename']} is ready.")
            except BackendError as error:
                st.error(f"{file.name}: {error}")
    st.caption("Up to 20 MiB per file. PDF, DOCX, UTF-8 text and Markdown; no OCR.")

try:
    documents = client.documents()
except BackendError as error:
    st.error(str(error))
    st.stop()

query = st.text_input(
    "Find a document", placeholder="Find a document", label_visibility="collapsed"
)
visible = [item for item in documents if query.casefold() in item["filename"].casefold()]
if not documents:
    st.info(
        "The shared library is empty. Add documents here, or attach private files inside a chat."
    )
elif not visible:
    st.caption("No documents match your search.")
for document in visible:
    st.divider()
    with st.container(horizontal=True, vertical_alignment="center"):
        with st.container():
            st.text(document["filename"])
            extension = document["filename"].rsplit(".", 1)[-1].upper()
            st.caption(
                f"{extension} · {format_file_size(document['size_bytes'])} · "
                f"{document['chunk_count']} excerpts · {document['status']}"
            )
        with st.popover("Delete", key=f"delete-library-{document['document_id']}"):
            st.caption(
                "Delete the original and its index? Existing chat messages keep their historical source excerpts."
            )
            if st.button("Delete document", key=f"delete-{document['document_id']}"):
                try:
                    with st.spinner("Removing the document..."):
                        client.delete(document["document_id"])
                    st.rerun()
                except BackendError as error:
                    st.error(str(error))
    if document.get("error"):
        st.warning(document["error"])
st.caption("Re-upload a failed file to retry indexing.")

with st.expander("Search library", icon=":material/search:"):
    with st.form("library-search"):
        search_query = st.text_input("Question or search terms")
        search_submitted = st.form_submit_button("Find excerpts")
    if search_submitted and search_query.strip():
        try:
            with st.spinner("Searching the shared library..."):
                sources = client.search(search_query, int(st.session_state.get("top_k", 5)))
            if sources:
                show_sources(sources)
            else:
                st.info("No shared-library excerpts were found.")
        except BackendError as error:
            st.error(str(error))

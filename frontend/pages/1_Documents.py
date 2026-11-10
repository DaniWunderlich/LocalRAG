"""Upload, inspect, retry and remove original documents."""

import streamlit as st

from api_client import BackendClient, BackendError

st.set_page_config(page_title="Documents ? Local RAG", page_icon="??")
st.title("Documents")
st.caption("PDF, DOCX, UTF-8 TXT and Markdown. Scanned PDFs require OCR and are not supported.")
client = BackendClient()

with st.form("upload", clear_on_submit=True):
    file = st.file_uploader("Choose a document", type=["pdf", "docx", "txt", "md", "markdown"])
    submitted = st.form_submit_button("Upload and index")
if submitted and file is not None:
    try:
        with st.spinner("Reading and indexing the document?"):
            document = client.upload(file.name, file.getvalue(), file.type)
        st.success(f"Indexed {document['filename']} ({document['chunk_count']} chunks).")
    except BackendError as error:
        st.error(str(error))

st.caption("To retry a failed indexing operation, upload the same file again.")
try:
    documents = client.documents()
except BackendError as error:
    st.error(str(error))
    st.stop()

if not documents:
    st.info("No documents have been uploaded yet.")
for document in documents:
    with st.container(border=True):
        st.text(document["filename"])
        st.caption(
            f"{document['content_type']} ? {document['size_bytes'] / 1024:.1f} KiB ? "
            f"{document['chunk_count']} chunks ? {document['status']} ? {document['uploaded_at']}"
        )
        if document.get("error"):
            st.warning(document["error"])
        confirmed = st.checkbox(
            "Remove this document and its index", key=f"confirm-{document['document_id']}"
        )
        if st.button(
            "Delete document", key=f"delete-{document['document_id']}", disabled=not confirmed
        ):
            try:
                with st.spinner("Removing the document?"):
                    client.delete(document["document_id"])
                st.rerun()
            except BackendError as error:
                st.error(str(error))

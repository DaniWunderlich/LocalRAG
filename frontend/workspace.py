"""Conversation navigation, inline attachments and a focused reading workspace."""

from typing import Any
from uuid import uuid4

import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile
from streamlit.typing import ChatInputValue

from api_client import BackendClient, BackendError
from ui import (
    backend_notice,
    format_file_size,
    initialise_preferences,
    install_composer_behaviour,
    show_sources,
)


def select_conversation(conversation_id: str) -> None:
    """Make a durable thread directly addressable after a browser reload."""
    st.session_state.active_chat_id = conversation_id
    st.query_params["chat"] = conversation_id


def new_conversation(client: BackendClient) -> dict[str, Any]:
    """Create a thread using the current defaults, then select it."""
    conversation = client.create_conversation(
        st.session_state.get("selected_model") or "",
        int(st.session_state.get("top_k", 5)),
        float(st.session_state.get("temperature", 0.2)),
    )
    if st.session_state.get("new_chat_use_library", False):
        conversation = client.update_conversation(conversation["conversation_id"], use_library=True)
    st.session_state.new_chat_use_library = False
    select_conversation(conversation["conversation_id"])
    return conversation


def conversation_rail(
    client: BackendClient, summaries: list[dict[str, Any]], active_id: str | None
) -> None:
    """Use a compact master list for the concrete task of switching conversations."""
    with st.sidebar:
        st.markdown('<div class="wordmark">LOCAL RAG</div>', unsafe_allow_html=True)
        st.caption("Your documents. Your conversations.")
        if st.button("New chat", icon=":material/add:", type="primary", width="stretch"):
            new_conversation(client)
            st.rerun()
        query = st.text_input(
            "Find a chat", placeholder="Find a chat", label_visibility="collapsed"
        )
        st.caption("CONVERSATIONS")
        matching = [item for item in summaries if query.casefold() in item["title"].casefold()]
        with st.container(height=430, border=False, key="conversation-list"):
            for item in matching:
                selected = item["conversation_id"] == active_id
                label = (
                    item["title"]
                    if item["status"] == "active"
                    else item["title"] + " · deletion pending"
                )
                if st.button(
                    label,
                    key=f"open-{item['conversation_id']}",
                    type="secondary" if selected else "tertiary",
                    width="stretch",
                    help=f"{item['message_count'] // 2} exchanges · {item['document_count']} attachments",
                ):
                    select_conversation(item["conversation_id"])
                    st.rerun()
            if not matching:
                st.caption(
                    "No matching chats." if summaries else "Your saved chats will appear here."
                )
        backend_notice()


def close_chat_settings() -> None:
    """Forget the open dialog when it is saved or dismissed."""
    st.session_state.pop("chat_settings_id", None)


@st.dialog("Chat model and settings", icon=":material/tune:", on_dismiss=close_chat_settings)
def chat_options(
    client: BackendClient,
    conversation: dict[str, Any] | None,
    names: list[str],
) -> None:
    """Keep model selection and infrequent edits together beside the composer."""
    conversation_id = conversation["conversation_id"] if conversation else "new"
    selected = conversation["model"] if conversation else st.session_state.get("selected_model")
    if names:
        model = st.selectbox(
            "Chat model",
            names,
            index=names.index(selected) if selected in names else None,
            placeholder="Choose a local model",
            key=f"model-{conversation_id}",
        )
        if model and model != selected:
            if conversation:
                client.update_conversation(conversation_id, model=model)
            else:
                st.session_state.selected_model = model
            st.rerun()
    else:
        st.warning("No local chat models are available.")
    with st.form(f"options-{conversation_id}"):
        title = (
            st.text_input("Chat name", value=conversation["title"], max_chars=120)
            if conversation
            else None
        )
        top_k = st.number_input(
            "Maximum source excerpts",
            min_value=1,
            max_value=20,
            value=int(conversation["top_k"] if conversation else st.session_state.get("top_k", 5)),
        )
        temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.0,
            value=float(
                conversation["temperature"]
                if conversation
                else st.session_state.get("temperature", 0.2)
            ),
            step=0.05,
        )
        if st.form_submit_button("Save changes"):
            if conversation:
                client.update_conversation(
                    conversation_id,
                    title=title,
                    top_k=top_k,
                    temperature=temperature,
                )
            else:
                st.session_state.top_k = top_k
                st.session_state.temperature = temperature
            close_chat_settings()
            st.rerun()
    if conversation:
        st.divider()
        st.caption("Deleting a chat also removes private files that no other chat uses.")
        confirmed = st.checkbox(
            "Delete this chat and its private files",
            key=f"confirm-chat-{conversation_id}",
        )
        if st.button("Delete chat", disabled=not confirmed, key="delete-chat"):
            client.delete_conversation(conversation_id)
            st.session_state.get("pending_submissions", {}).pop(conversation_id, None)
            st.session_state.active_chat_id = None
            st.query_params.pop("chat", None)
            close_chat_settings()
            st.rerun()


def library_options(client: BackendClient, conversation: dict[str, Any] | None) -> None:
    """Make the shared evidence scope explicit and reachable without scrolling."""
    conversation_id = conversation["conversation_id"] if conversation else "new"
    included = bool(
        conversation["use_library"]
        if conversation
        else st.session_state.get("new_chat_use_library", False)
    )
    label = "Exclude shared library" if included else "Include shared library"
    if st.button(
        label,
        icon=":material/library_add_check:" if included else ":material/library_books:",
        key="composer-library",
        help=(
            "Shared library included. Click to exclude it."
            if included
            else "Shared library excluded. Click to include it."
        ),
        type="primary" if included else "tertiary",
        width=40,
    ):
        if conversation:
            client.update_conversation(conversation_id, use_library=not included)
        else:
            st.session_state.new_chat_use_library = not included
        st.rerun()


def composer(
    client: BackendClient,
    conversation: dict[str, Any] | None,
    names: list[str],
    disabled: bool,
) -> str | ChatInputValue | None:
    """Keep the input, model settings and evidence controls in one pinned surface."""
    conversation_id = conversation["conversation_id"] if conversation else "new"
    with st.bottom, st.container(key="composer-shell"):
        prompt = st.chat_input(
            "Ask about your documents, or attach files",
            key=f"composer-{conversation_id}",
            max_chars=8000,
            height=112,
            accept_file="multiple",
            file_type=["pdf", "docx", "txt", "md", "markdown"],
            max_upload_size=20,
            disabled=disabled,
        )
        with st.container(
            horizontal=True,
            vertical_alignment="center",
            gap="small",
            key="composer-tools",
        ):
            model = (
                conversation["model"] if conversation else st.session_state.get("selected_model")
            )
            if st.button(
                "Chat model and settings",
                icon=":material/tune:",
                help=f"Chat settings ({model})" if model else "Choose a local chat model",
                key="composer-settings",
                type="tertiary",
                width=40,
            ):
                st.session_state.chat_settings_id = conversation_id
            library_options(client, conversation)
        install_composer_behaviour()
    if st.session_state.get("chat_settings_id") == conversation_id:
        chat_options(client, conversation, names)
    return prompt


def show_attachments(client: BackendClient, conversation: dict[str, Any]) -> None:
    """Present real attachment status and a contextual remove action."""
    documents = client.attachments(conversation["conversation_id"])
    if not documents:
        return
    with st.expander(
        f"Chat documents · {len(documents)}",
        icon=":material/attach_file:",
        expanded=not conversation["messages"],
    ):
        for document in documents:
            with st.container(horizontal=True, vertical_alignment="center"):
                with st.container():
                    st.text(document["filename"])
                    st.caption(
                        f"{format_file_size(document['size_bytes'])} · "
                        f"{document['chunk_count']} excerpts · {document['status']}"
                    )
                with st.popover("Remove", key=f"remove-{document['document_id']}"):
                    st.caption(
                        "Remove this attachment from the chat? Unshared private files are also deleted."
                    )
                    if st.button("Remove attachment", key=f"detach-{document['document_id']}"):
                        client.detach(conversation["conversation_id"], document["document_id"])
                        st.rerun()
            if document.get("error"):
                st.warning(document["error"])


def submit_pending(client: BackendClient, conversation_id: str) -> None:
    """Retry safely without re-creating successful uploads or duplicate exchanges."""
    pending = st.session_state.pending_submissions[conversation_id]
    try:
        with st.spinner("Indexing attachments and preparing an answer..."):
            for file in pending["files"]:
                client.upload_attachment(
                    pending["conversation_id"],
                    file.name,
                    file.getvalue(),
                    file.type,
                )
            if pending["text"].strip():
                client.send_message(
                    pending["conversation_id"],
                    pending["text"],
                    pending["request_id"],
                )
        del st.session_state.pending_submissions[conversation_id]
        st.rerun()
    except BackendError as error:
        pending["error"] = str(error)
        st.rerun()


def render_workspace() -> None:
    """Restore saved conversations and accept text, documents or both together."""
    client = BackendClient()
    if "pending_submissions" not in st.session_state:
        st.session_state.pending_submissions = {}
    legacy_messages = st.session_state.get("messages")
    if legacy_messages:
        if "legacy_import_id" not in st.session_state:
            st.session_state.legacy_import_id = str(uuid4())
        restored = client.import_conversation(
            st.session_state.legacy_import_id,
            legacy_messages,
            st.session_state.get("selected_model") or "",
            int(st.session_state.get("top_k", 5)),
            float(st.session_state.get("temperature", 0.2)),
        )
        select_conversation(restored["conversation_id"])
        del st.session_state.messages
    try:
        summaries = client.conversations()
    except BackendError as error:
        st.title("Chats")
        st.error(str(error))
        st.caption(
            "Saved conversations remain on the local volume. Retry when the backend is available."
        )
        if st.button("Try again"):
            st.rerun()
        return
    try:
        names = initialise_preferences()
    except BackendError:
        names = []
        st.warning("Ollama is unavailable. You can still browse saved chats.")
    active_id = st.query_params.get("chat") or st.session_state.get("active_chat_id")
    if active_id not in {item["conversation_id"] for item in summaries}:
        active_id = None
        st.session_state.active_chat_id = None
        st.query_params.pop("chat", None)
    conversation_rail(client, summaries, active_id)
    conversation = client.conversation(active_id) if active_id else None
    st.title(conversation["title"] if conversation else "New chat")
    if conversation:
        if conversation["status"] != "active":
            st.warning(
                "This chat is awaiting deletion. Retry to finish removing its private files."
            )
            if st.button("Retry deletion"):
                client.delete_conversation(conversation["conversation_id"])
                st.rerun()
            return
        show_attachments(client, conversation)
    else:
        st.caption(
            "Attach a document below, then ask a question. Chats are saved on this computer."
        )
    messages = conversation["messages"] if conversation else []
    with st.container(key="transcript"):
        for message in messages:
            with st.container(key=f"turn-{message['message_id']}"):
                st.caption("YOU" if message["role"] == "user" else "LOCAL RAG")
                st.markdown(message["content"])
                show_sources(message.get("sources", []))
        if not messages and conversation:
            st.caption(
                "Ask about the attached documents."
                if conversation["document_ids"]
                else "Attach documents, or include the shared library, to give this chat its evidence."
            )
    pending = st.session_state.pending_submissions.get(active_id)
    if pending and pending["conversation_id"] == active_id:
        st.error(pending["error"])
        if pending["text"]:
            st.text(pending["text"])
        with st.container(horizontal=True):
            if st.button("Retry submission"):
                submit_pending(client, pending["conversation_id"])
            if st.button("Discard draft", type="tertiary"):
                del st.session_state.pending_submissions[pending["conversation_id"]]
                st.rerun()
    prompt = composer(
        client,
        conversation,
        names,
        disabled=bool(pending and pending["conversation_id"] == active_id),
    )
    if prompt:
        text: str = prompt if isinstance(prompt, str) else prompt.text
        files: list[UploadedFile] = [] if isinstance(prompt, str) else prompt.files
        if not text.strip() and not files:
            return
        if conversation is None:
            conversation = new_conversation(client)
        st.session_state.pending_submissions[conversation["conversation_id"]] = {
            "conversation_id": conversation["conversation_id"],
            "text": text,
            "files": files,
            "request_id": str(uuid4()),
            "error": "",
        }
        submit_pending(client, conversation["conversation_id"])


def render() -> None:
    """Keep transport errors visible without exposing tracebacks or losing drafts."""
    try:
        render_workspace()
    except BackendError as error:
        st.error(str(error))

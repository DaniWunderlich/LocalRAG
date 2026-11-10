"""Native Gradio components for the local conversation and document workspace."""

from collections.abc import Callable
from html import escape
from pathlib import Path
from typing import Any

import gradio as gr

from api_client import BackendError
from workspace import (
    FILE_TYPES,
    Draft,
    Session,
    Workspace,
    document_rows,
    source_details,
    transcript,
)

ASSETS = Path(__file__).parent / "assets"
ROOT = Path(__file__).parent


def reading_theme() -> gr.themes.Base:
    """Use local system fonts and the established paper, ink and evergreen palette."""
    return gr.themes.Base(
        font=["Segoe UI", "system-ui", "sans-serif"],
        font_mono=["Cascadia Code", "Consolas", "monospace"],
    ).set(
        body_background_fill="#faf9f6",
        body_background_fill_dark="#171c19",
        body_text_color="#232c28",
        body_text_color_dark="#ebeee9",
        body_text_color_subdued="#59645d",
        body_text_color_subdued_dark="#b2beb4",
        block_background_fill="#faf9f6",
        block_background_fill_dark="#171c19",
        background_fill_primary="#ffffff",
        background_fill_primary_dark="#202722",
        background_fill_secondary="#eeede7",
        background_fill_secondary_dark="#252d28",
        block_border_color="#d4d9d1",
        block_border_color_dark="#46544b",
        border_color_primary="#d4d9d1",
        border_color_primary_dark="#46544b",
        input_background_fill="#ffffff",
        input_background_fill_dark="#252d28",
        input_border_color="#d4d9d1",
        input_border_color_dark="#46544b",
        input_border_color_focus="#d4d9d1",
        input_border_color_focus_dark="#46544b",
        input_placeholder_color="#59645d",
        input_placeholder_color_dark="#b2beb4",
        input_shadow="none",
        input_shadow_focus="none",
        input_shadow_dark="none",
        input_shadow_focus_dark="none",
        button_primary_background_fill="#245b49",
        button_primary_background_fill_dark="#8fc7af",
        button_primary_background_fill_hover="#1d4c3c",
        button_primary_background_fill_hover_dark="#a5d4be",
        button_primary_text_color="#ffffff",
        button_primary_text_color_dark="#17231c",
        button_primary_border_color="#245b49",
        button_primary_border_color_dark="#8fc7af",
        button_secondary_background_fill="#ffffff",
        button_secondary_background_fill_dark="#252d28",
        button_secondary_text_color="#232c28",
        button_secondary_text_color_dark="#ebeee9",
        button_secondary_border_color="#d4d9d1",
        button_secondary_border_color_dark="#46544b",
        shadow_drop="none",
        shadow_drop_lg="none",
        button_primary_shadow="none",
        button_secondary_shadow="none",
        link_text_color="#245b49",
        link_text_color_dark="#8fc7af",
    )


def create_workspace(workspace: Workspace | None = None) -> gr.Blocks:
    """Build callbacks around an HTTP client and an independent state per browser."""
    controller = workspace or Workspace()
    demo = gr.Blocks(
        title="Local RAG", analytics_enabled=False, fill_height=True, delete_cache=(3600, 86400)
    )
    with demo:
        state = gr.State(Session())
        requested_chat = gr.Textbox(visible=False)
        with gr.Sidebar(label="Conversations", open=False, elem_id="conversation-rail", width=280):
            gr.HTML(
                '<div class="wordmark">LOCAL RAG</div><p class="muted">Your documents. Your conversations.</p>'
            )
            new_chat = gr.Button(
                "New chat", variant="primary", icon=ASSETS / "add.svg", elem_id="new-chat"
            )
            find_chat = gr.Textbox(label="Find a chat", placeholder="Find a chat", show_label=False)
            chats = gr.Radio(
                choices=[],
                label="Conversations",
                show_label=False,
                interactive=True,
                elem_id="conversation-list",
            )
            refresh = gr.Button("Refresh", size="sm")
            service_notice = gr.Markdown(elem_id="service-notice")
        with gr.Row(elem_id="workspace-header"):
            gr.HTML(
                '<a href="#conversation-workspace" class="skip-link">Skip to conversation</a><span class="wordmark">LOCAL RAG</span>'
            )
            appearance_control = gr.Radio(
                ["Light", "Dark", "System"],
                value="System",
                label="Appearance",
                show_label=False,
                container=False,
                elem_id="appearance",
                interactive=False,
            )
        error = gr.Textbox(
            label="Workspace notice", interactive=False, visible=False, elem_id="workspace-error"
        )
        marker = gr.HTML('<span data-active-chat=""></span>', elem_id="active-chat-marker")
        with gr.Tabs(elem_id="workspace-tabs") as tabs:
            with gr.Tab("Chats", id="chats"), gr.Column(elem_id="conversation-workspace"):
                title = gr.Markdown("# New chat", elem_id="chat-title")
                with gr.Accordion("Chat documents", open=False, visible=False) as attachment_panel:
                    attachment_table = gr.Dataframe(
                        headers=["Filename", "Size", "Excerpts", "Status", "Error"],
                        datatype=["str", "str", "number", "str", "str"],
                        type="array",
                        interactive=False,
                        max_height=180,
                        elem_id="attachment-table",
                    )
                    attachment_selection = gr.Textbox(
                        label="Selected attachment", interactive=False
                    )
                    detach_confirm = gr.Checkbox(label="Remove this attachment from the chat")
                    detach = gr.Button("Remove attachment", size="sm")
                chat = gr.Chatbot(
                    label="Conversation",
                    show_label=False,
                    layout="panel",
                    height="100%",
                    buttons=["copy"],
                    feedback_options=[],
                    allow_file_downloads=False,
                    allow_tags=False,
                    autoscroll=True,
                    elem_id="transcript",
                    placeholder="Attach a document below, then ask a question. Chats are saved on this computer.",
                )
                with gr.Column(visible=False, elem_id="pending-submission") as pending_panel:
                    gr.Markdown(
                        "The unfinished submission stays with this chat. Retry it using the same request ID, or discard it."
                    )
                    with gr.Row():
                        retry = gr.Button("Retry submission", variant="primary")
                        discard = gr.Button("Discard draft")
                with gr.Column(elem_id="composer-shell"):
                    composer = gr.MultimodalTextbox(
                        label="Message",
                        show_label=False,
                        placeholder="Ask about your documents, or attach files",
                        file_types=FILE_TYPES,
                        file_count="multiple",
                        sources=["upload"],
                        lines=2,
                        max_lines=8,
                        max_plain_text_length=8000,
                        interactive=True,
                        elem_id="composer",
                    )
                    with gr.Row(elem_id="composer-actions"):
                        settings = gr.Button(
                            "Chat model and settings",
                            icon=ASSETS / "settings.svg",
                            min_width=40,
                            scale=0,
                            elem_id="composer-settings",
                            elem_classes="icon-button",
                        )
                        library = gr.Button(
                            "Include shared library",
                            icon=ASSETS / "library.svg",
                            min_width=40,
                            scale=0,
                            elem_id="composer-library",
                            elem_classes="icon-button",
                        )
                    gr.HTML(
                        '<button id="jump-to-latest" type="button" aria-label="Jump to latest message" title="Jump to latest message" hidden><svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 5v14m-6-6 6 6 6-6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button>',
                        elem_id="jump-control",
                    )
            with gr.Tab("Library", id="library"):
                gr.Markdown(
                    "# Document library\nDocuments here can be included in any chat. Chat attachments stay with their conversation."
                )
                library_upload = gr.File(
                    label="Add documents",
                    file_count="multiple",
                    file_types=FILE_TYPES,
                    type="filepath",
                )
                upload = gr.Button("Add to library", variant="primary")
                gr.Markdown("Up to 20 MiB per file. PDF, DOCX, UTF-8 text and Markdown; no OCR.")
                find_document = gr.Textbox(
                    label="Find a document", placeholder="Find a document", show_label=False
                )
                document_table = gr.Dataframe(
                    headers=["Filename", "Size", "Excerpts", "Status", "Error"],
                    datatype=["str", "str", "number", "str", "str"],
                    type="array",
                    interactive=False,
                    elem_id="document-table",
                )
                document_selection = gr.Textbox(label="Selected document", interactive=False)
                delete_document_confirm = gr.Checkbox(
                    label="Delete the selected original and its index"
                )
                delete_document = gr.Button("Delete document", size="sm")
                with gr.Accordion("Search library", open=False):
                    query = gr.Textbox(label="Question or search terms", max_length=8000)
                    search = gr.Button("Find excerpts")
                    search_results = gr.HTML()
            with gr.Tab("Settings", id="settings"):
                gr.Markdown(
                    "# Settings\nEach saved chat keeps its own model, document scope and generation settings."
                )
                gr.Markdown(
                    "## Appearance\nUse Light, Dark or System at the top of the workspace. The browser remembers this choice."
                )
                show_sources = gr.Checkbox(label="Show source excerpts", value=True)
                gr.Markdown("## New chat defaults")
                default_model = gr.Dropdown(label="Chat model", choices=[], interactive=True)
                default_top_k = gr.Slider(1, 20, step=1, value=5, label="Maximum source excerpts")
                default_temperature = gr.Slider(0, 1, step=0.05, value=0.2, label="Temperature")
                save_defaults = gr.Button("Save defaults")
                gr.Markdown(
                    "These defaults and reading preferences apply to this browser session. The embedding model is managed by the backend to keep the document index compatible."
                )
        with gr.Column(visible=False, elem_id="chat-settings") as settings_panel:
            gr.Markdown("## Chat model and settings", elem_id="chat-settings-title")
            chat_model = gr.Dropdown(label="Chat model", choices=[], interactive=True)
            chat_name = gr.Textbox(label="Chat name", max_length=120)
            top_k = gr.Slider(1, 20, step=1, value=5, label="Maximum source excerpts")
            temperature = gr.Slider(0, 1, step=0.05, value=0.2, label="Temperature")
            with gr.Row():
                save = gr.Button("Save changes", variant="primary")
                close = gr.Button("Close", elem_id="close-chat-settings")
            gr.Markdown("Deleting a chat also removes private files that no other chat uses.")
            delete_confirm = gr.Checkbox(label="Delete this chat and its private files")
            delete_chat = gr.Button("Delete chat", variant="stop")

        def render(session: Session, restore_composer: bool = False) -> dict[Any, Any]:
            """Update only native components, with durable values read from the backend."""
            conversation = session.conversation or {}
            choices = [
                (
                    item["title"] + (" - deletion pending" if item["status"] != "active" else ""),
                    item["conversation_id"],
                )
                for item in session.summaries
                if session.chat_query.casefold() in item["title"].casefold()
            ]
            model = conversation.get("model", session.model)
            names = session.models + ([model] if model and model not in session.models else [])
            pending = session.key in session.pending
            values: dict[Any, Any] = {
                state: session,
                chats: gr.Radio(
                    choices=choices,
                    value=session.active_id
                    if session.active_id in {value for _, value in choices}
                    else None,
                ),
                title: "# " + escape(conversation.get("title", "New chat")),
                chat: transcript(session),
                library: gr.Button(
                    value="Exclude shared library"
                    if session.use_library
                    else "Include shared library",
                    icon=ASSETS / ("library-check.svg" if session.use_library else "library.svg"),
                    variant="primary" if session.use_library else "secondary",
                ),
                error: gr.Textbox(value=session.error, visible=bool(session.error)),
                service_notice: session.service_notice,
                marker: '<span data-ready="'
                + str(session.initialised).lower()
                + '" data-active-chat="'
                + escape(session.active_id or "", quote=True)
                + '" data-message-count="'
                + str(len(conversation.get("messages", [])))
                + '"></span>',
                attachment_panel: gr.Accordion(visible=bool(session.attachments)),
                attachment_table: document_rows(session.attachments),
                attachment_selection: next(
                    (
                        item["filename"]
                        for item in session.attachments
                        if item["document_id"] == session.selected_attachment
                    ),
                    "",
                ),
                document_table: document_rows(controller.visible_documents(session)),
                document_selection: next(
                    (
                        item["filename"]
                        for item in session.documents
                        if item["document_id"] == session.selected_document
                    ),
                    "",
                ),
                pending_panel: gr.update(visible=pending),
                chat_model: gr.Dropdown(choices=names, value=model or None),
                chat_name: gr.Textbox(
                    value=conversation.get("title", ""), visible=bool(conversation)
                ),
                top_k: conversation.get("top_k", session.top_k),
                temperature: conversation.get("temperature", session.temperature),
                default_model: gr.Dropdown(choices=session.models, value=session.model or None),
                default_top_k: session.top_k,
                default_temperature: session.temperature,
                delete_chat: gr.Button(interactive=bool(session.active_id)),
                delete_confirm: False,
            }
            if restore_composer:
                values[composer] = gr.MultimodalTextbox(
                    value=session.drafts.get(session.key, Draft()).payload(),
                    interactive=not pending and conversation.get("status", "active") == "active",
                )
            return values

        def perform(
            session: Session,
            payload: dict[str, Any] | None,
            action: Callable[[], None],
            restore: bool = False,
        ) -> dict[Any, Any]:
            """Retain drafts and show actionable transport failures instead of tracebacks."""
            session.remember(payload)
            session.error = ""
            try:
                action()
            except BackendError as failure:
                session.error = str(failure)
            except OSError:
                session.error = "The temporary upload is unavailable. Attach the file again."
            return render(session, restore)

        def initialise(session: Session, requested: str, mode: str) -> dict[Any, Any]:
            """Restore the addressable chat when the page establishes its Gradio session."""
            result = perform(session, None, lambda: controller.initialise(session, requested), True)
            result[appearance_control] = gr.Radio(
                value=mode if mode in {"Light", "Dark", "System"} else "System", interactive=True
            )
            return result

        def create_chat(session: Session, payload: dict[str, Any] | None) -> dict[Any, Any]:
            result = perform(session, payload, lambda: controller.new(session, payload), True)
            result.update(
                {
                    tabs: gr.Tabs(selected="chats"),
                    settings_panel: gr.update(visible=False),
                    detach_confirm: False,
                }
            )
            return result

        def select_chat(
            session: Session, selected: str | None, payload: dict[str, Any] | None
        ) -> dict[Any, Any]:
            result = perform(
                session,
                payload,
                lambda: controller.select(session, selected, payload) if selected else None,
                True,
            )
            result.update(
                {
                    tabs: gr.Tabs(selected="chats"),
                    settings_panel: gr.update(visible=False),
                    detach_confirm: False,
                }
            )
            return result

        def submit(session: Session, payload: dict[str, Any] | None) -> dict[Any, Any]:
            return perform(session, payload, lambda: controller.submit(session, payload), True)

        def open_settings(session: Session, payload: dict[str, Any] | None) -> dict[Any, Any]:
            session.remember(payload)
            result = render(session)
            result[settings_panel] = gr.update(visible=True)
            return result

        def save_settings(
            session: Session,
            payload: dict[str, Any] | None,
            name: str,
            model: str | None,
            count: float,
            heat: float,
        ) -> dict[Any, Any]:
            result = perform(
                session,
                payload,
                lambda: controller.save_settings(session, name, model, int(count), heat),
            )
            result[settings_panel] = gr.update(visible=bool(session.error))
            return result

        def remove_chat(
            session: Session, payload: dict[str, Any] | None, confirmed: bool
        ) -> dict[Any, Any]:
            result = perform(
                session, payload, lambda: controller.delete_chat(session, confirmed), True
            )
            result[settings_panel] = gr.update(visible=bool(session.error))
            return result

        def filter_chats(session: Session, text: str) -> dict[Any, Any]:
            session.chat_query = text
            result = render(session)
            return {state: session, chats: result[chats]}

        def filter_documents(session: Session, text: str) -> dict[Any, Any]:
            session.library_query = text
            session.selected_document = None
            return {
                state: session,
                document_table: document_rows(controller.visible_documents(session)),
                document_selection: "",
                delete_document_confirm: False,
            }

        def select_document(session: Session, event: gr.SelectData) -> dict[Any, Any]:
            index = event.index[0] if isinstance(event.index, (list, tuple)) else event.index
            rows = controller.visible_documents(session)
            if isinstance(index, int) and 0 <= index < len(rows):
                session.selected_document = rows[index]["document_id"]
                return {
                    state: session,
                    document_selection: rows[index]["filename"],
                    delete_document_confirm: False,
                }
            return {state: session}

        def select_attachment(session: Session, event: gr.SelectData) -> dict[Any, Any]:
            index = event.index[0] if isinstance(event.index, (list, tuple)) else event.index
            if isinstance(index, int) and 0 <= index < len(session.attachments):
                session.selected_attachment = session.attachments[index]["document_id"]
                return {
                    state: session,
                    attachment_selection: session.attachments[index]["filename"],
                    detach_confirm: False,
                }
            return {state: session}

        def upload_documents(
            session: Session, payload: dict[str, Any] | None, files: list[str] | None
        ) -> dict[Any, Any]:
            result = perform(session, payload, lambda: controller.upload_library(session, files))
            if not session.error:
                result[library_upload] = None
            return result

        def remove_document(
            session: Session, payload: dict[str, Any] | None, confirmed: bool
        ) -> dict[Any, Any]:
            result = perform(
                session, payload, lambda: controller.delete_document(session, confirmed)
            )
            result[delete_document_confirm] = False
            return result

        def remove_attachment(
            session: Session, payload: dict[str, Any] | None, confirmed: bool
        ) -> dict[Any, Any]:
            result = perform(session, payload, lambda: controller.detach(session, confirmed))
            result[detach_confirm] = False
            return result

        def search_library(session: Session, text: str) -> dict[Any, Any]:
            try:
                sources = controller.client.search(text, session.top_k) if text.strip() else []
                return {
                    search_results: source_details(sources, session.show_sources)
                    or "No shared-library excerpts were found."
                }
            except BackendError as failure:
                return {error: gr.Textbox(value=str(failure), visible=True)}

        def defaults(
            session: Session, model: str | None, count: float, heat: float, excerpts: bool
        ) -> dict[Any, Any]:
            session.model, session.top_k, session.temperature, session.show_sources = (
                model or "",
                int(count),
                heat,
                excerpts,
            )
            return render(session)

        outputs = [
            state,
            chats,
            title,
            chat,
            library,
            error,
            service_notice,
            marker,
            attachment_panel,
            attachment_table,
            attachment_selection,
            document_table,
            document_selection,
            pending_panel,
            chat_model,
            chat_name,
            top_k,
            temperature,
            default_model,
            default_top_k,
            default_temperature,
            delete_chat,
            delete_confirm,
            composer,
            tabs,
            settings_panel,
            detach_confirm,
            delete_document_confirm,
            library_upload,
            search_results,
            appearance_control,
        ]
        options: dict[str, Any] = {
            "outputs": outputs,
            "api_visibility": "private",
            "concurrency_id": "workspace",
            "concurrency_limit": 1,
            "show_progress": "minimal",
        }
        demo.load(
            initialise,
            inputs=[state, requested_chat, appearance_control],
            js='(state) => {let mode="System";try {mode=(localStorage.getItem("localrag-appearance")||"system");mode=mode.charAt(0).toUpperCase()+mode.slice(1)}catch{}return [state,new URL(window.location.href).searchParams.get("chat")||"",mode]}',
            **options,
        )
        appearance_control.input(
            fn=None,
            inputs=appearance_control,
            outputs=None,
            queue=False,
            js="mode => {window.__localRagSetAppearance?.(mode);}",
            api_visibility="private",
        )
        new_chat.click(create_chat, inputs=[state, composer], **options)
        chats.input(select_chat, inputs=[state, chats, composer], **options)
        composer.submit(submit, inputs=[state, composer], **options)
        settings.click(open_settings, inputs=[state, composer], **options)
        close.click(
            lambda: gr.update(visible=False),
            outputs=settings_panel,
            queue=False,
            api_visibility="private",
        )
        library.click(
            lambda session, payload: perform(
                session, payload, lambda: controller.toggle_library(session)
            ),
            inputs=[state, composer],
            **options,
        )
        save.click(
            save_settings,
            inputs=[state, composer, chat_name, chat_model, top_k, temperature],
            **options,
        )
        delete_chat.click(remove_chat, inputs=[state, composer, delete_confirm], **options)
        retry.click(
            lambda session, payload: perform(
                session, payload, lambda: controller.retry(session), True
            ),
            inputs=[state, composer],
            **options,
        )
        discard.click(
            lambda session, payload: perform(
                session, payload, lambda: controller.discard(session), True
            ),
            inputs=[state, composer],
            **options,
        )
        refresh.click(
            lambda session, payload: perform(
                session, payload, lambda: controller.initialise(session)
            ),
            inputs=[state, composer],
            **options,
        )
        find_chat.input(filter_chats, inputs=[state, find_chat], **options)
        find_document.input(filter_documents, inputs=[state, find_document], **options)
        document_table.select(select_document, inputs=[state], **options)
        attachment_table.select(select_attachment, inputs=[state], **options)
        upload.click(upload_documents, inputs=[state, composer, library_upload], **options)
        delete_document.click(
            remove_document, inputs=[state, composer, delete_document_confirm], **options
        )
        detach.click(remove_attachment, inputs=[state, composer, detach_confirm], **options)
        search.click(search_library, inputs=[state, query], **options)
        save_defaults.click(
            defaults,
            inputs=[state, default_model, default_top_k, default_temperature, show_sources],
            **options,
        )
        show_sources.input(
            defaults,
            inputs=[state, default_model, default_top_k, default_temperature, show_sources],
            **options,
        )
    demo.queue(max_size=32, default_concurrency_limit=1)
    return demo

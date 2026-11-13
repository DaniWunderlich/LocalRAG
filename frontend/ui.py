"""Native Gradio components for the local conversation and document workspace."""

from collections.abc import Callable, Iterator
from html import escape
from pathlib import Path
from typing import Any

import gradio as gr

from api_client import BackendError
from localization import GERMAN, translate
from navigation import RAIL_JS, chat_navigation
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
            find_chat = gr.Textbox(
                label="Find a chat",
                placeholder="Find a chat",
                show_label=False,
                container=False,
                elem_id="find-chat",
            )
            chats = gr.HTML(
                "",
                elem_id="conversation-list",
                js_on_load=RAIL_JS,
            )
            refresh = gr.Button("Refresh", size="sm")
            service_notice = gr.Markdown(elem_id="service-notice")
        with gr.Row(elem_id="workspace-header"):
            gr.HTML(
                '<a href="#conversation-workspace" class="skip-link">Skip to conversation</a><span class="wordmark">LOCAL RAG</span>'
            )
            appearance_control = gr.Radio(
                [("☀", "Light"), ("☾", "Dark"), ("▣", "System")],
                value="System",
                label="Appearance",
                show_label=False,
                container=False,
                elem_id="appearance",
                interactive=False,
            )
            language_control = gr.Radio(
                [("🇩🇪", "de"), ("🇬🇧", "en")],
                value="en",
                label="Language",
                show_label=False,
                container=False,
                elem_id="language",
                min_width=90,
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
                    placeholder="Ask a question to start. Attach documents for answers based on your files.",
                )
                with gr.Column(visible=False, elem_id="pending-submission") as pending_panel:
                    gr.Markdown(
                        "The unfinished submission stays with this chat. Retry it using the same request ID, or discard it."
                    )
                    with gr.Row():
                        retry = gr.Button(
                            "Retry submission", variant="primary", elem_id="retry-submission"
                        )
                        discard = gr.Button("Discard draft")
                submission_status = gr.HTML(
                    visible=False, elem_id="submission-status", js_on_load=None
                )
                with gr.Column(elem_id="composer-shell"):
                    composer = gr.MultimodalTextbox(
                        label="Message",
                        show_label=False,
                        placeholder="Ask a question, or attach documents",
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
                    # Register both states on the live component before callback updates.
                    library_icons = {
                        False: library.icon,
                        True: library.serve_static_file(ASSETS / "library-check.svg"),
                    }
                    for icon in library_icons.values():
                        if icon:
                            library.keep_in_cache.add(icon["path"])
                    gr.HTML(
                        '<button id="jump-to-latest" type="button" aria-label="Jump to latest message" title="Jump to latest message" hidden><svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 5v14m-6-6 6 6 6-6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button>',
                        elem_id="jump-control",
                    )
                scope_notice = gr.Markdown(visible=False, elem_id="scope-notice")
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

        with gr.Column(visible=False, elem_id="chat-manager") as manager_panel:
            manager_title = gr.Markdown("## Manage chat", elem_id="chat-manager-title")
            manager_context = gr.Markdown(elem_id="chat-manager-context")
            manager_notice = gr.Markdown(visible=False, elem_id="manager-notice")
            with gr.Column(elem_id="manager-rename") as manager_rename:
                manager_name = gr.Textbox(label="Chat name", max_length=120, elem_id="manager-name")
            with gr.Column(elem_id="manager-move") as manager_move:
                manager_folder = gr.Radio(
                    label="Destination folder",
                    choices=[],
                    interactive=True,
                    elem_id="manager-folder",
                )
                manager_new_folder = gr.Textbox(
                    label="New folder name",
                    placeholder="Enter a folder name",
                    max_length=80,
                    visible=False,
                    elem_id="manager-new-folder",
                )
            with gr.Column(elem_id="manager-removal") as manager_removal:
                gr.Markdown("Deleting a chat also removes private files that no other chat uses.")
                manager_confirm = gr.Checkbox(label="Delete this chat and its private files")
            with gr.Row(elem_id="manager-actions"):
                manager_save = gr.Button("Save changes", variant="primary")
                manager_delete = gr.Button("Delete chat", variant="stop", visible=False)
                manager_close = gr.Button("Cancel", elem_id="close-chat-manager")

        # Capture original component strings once; locale changes update native labels too.
        localized: dict[Any, dict[str, Any]] = {}
        for component in list(demo.blocks.values()):
            fields: dict[str, Any] = {}
            for attribute in ("label", "placeholder", "value", "headers"):
                if attribute == "value" and not isinstance(
                    component, (gr.Button, gr.Markdown, gr.HTML)
                ):
                    continue
                value = getattr(component, attribute, None)
                if (isinstance(value, str) and value in GERMAN) or (
                    attribute == "headers" and isinstance(value, list)
                ):
                    fields[attribute] = value
            if fields:
                localized[component] = fields

        def locale_updates(session: Session) -> dict[Any, Any]:
            updates = {}
            for component, fields in localized.items():
                properties: dict[str, Any] = {
                    key: [translate(item, session.language) for item in value]
                    if isinstance(value, list)
                    else translate(value, session.language)
                    for key, value in fields.items()
                }
                updates[component] = gr.update(**properties)
            return updates

        def render(session: Session, restore_composer: bool = False) -> dict[Any, Any]:
            """Update only native components, with durable values read from the backend."""
            conversation = session.conversation or {}
            model = conversation.get("model", session.model)
            names = session.models + ([model] if model and model not in session.models else [])
            pending = session.key in session.pending

            def tr(value: str) -> str:
                return translate(value, session.language)

            values: dict[Any, Any] = locale_updates(session)
            dynamic: dict[Any, Any] = {
                state: session,
                manager_notice: gr.update(value=tr(session.error), visible=bool(session.error)),
                manager_title: "## "
                + tr(
                    {"rename": "Rename chat", "move": "Move to folder", "delete": "Delete chat"}[
                        session.managed_action
                    ]
                ),
                manager_rename: gr.update(visible=session.managed_action == "rename"),
                manager_move: gr.update(visible=session.managed_action == "move"),
                manager_removal: gr.update(visible=session.managed_action == "delete"),
                manager_save: gr.update(
                    value=tr("Move chat" if session.managed_action == "move" else "Save changes"),
                    visible=session.managed_action != "delete",
                ),
                manager_delete: gr.update(visible=session.managed_action == "delete"),
                submission_status: gr.update(value="", visible=False),
                scope_notice: gr.update(
                    value=tr(
                        "General chat: ask any question, or attach documents for document answers."
                    ),
                    visible=not session.attachments
                    and not (session.use_library and session.documents),
                ),
                chats: chat_navigation(session),
                title: "# " + escape(conversation.get("title") or tr("New chat")),
                chat: transcript(session),
                library: gr.update(
                    value=tr("Exclude shared library")
                    if session.use_library
                    else tr("Include shared library"),
                    icon=library_icons[session.use_library],
                    variant="primary" if session.use_library else "secondary",
                ),
                error: gr.update(value=tr(session.error), visible=bool(session.error)),
                service_notice: tr(session.service_notice),
                marker: '<span data-ready="'
                + str(session.initialised).lower()
                + '" data-active-chat="'
                + escape(session.active_id or "", quote=True)
                + '" data-language="'
                + session.language
                + '" data-message-count="'
                + str(len(conversation.get("messages", [])))
                + '" data-pending-submission="'
                + str(pending).lower()
                + '"></span>',
                attachment_panel: gr.update(visible=bool(session.attachments)),
                attachment_table: document_rows(session.attachments, session.language),
                attachment_selection: next(
                    (
                        item["filename"]
                        for item in session.attachments
                        if item["document_id"] == session.selected_attachment
                    ),
                    "",
                ),
                document_table: document_rows(
                    controller.visible_documents(session), session.language
                ),
                document_selection: next(
                    (
                        item["filename"]
                        for item in session.documents
                        if item["document_id"] == session.selected_document
                    ),
                    "",
                ),
                pending_panel: gr.update(visible=pending),
                chat_model: gr.update(choices=names, value=model or None),
                chat_name: gr.update(
                    value=conversation.get("title", ""), visible=bool(conversation)
                ),
                top_k: conversation.get("top_k", session.top_k),
                temperature: conversation.get("temperature", session.temperature),
                default_model: gr.update(choices=session.models, value=session.model or None),
                default_top_k: session.top_k,
                default_temperature: session.temperature,
                delete_chat: gr.update(interactive=bool(session.active_id)),
                delete_confirm: False,
            }
            # Merge localized properties with dynamic values so labels survive updates.
            for component, value in dynamic.items():
                if component in values and isinstance(value, dict):
                    values[component].update(value)
                elif component in values:
                    values[component]["value"] = value
                else:
                    values[component] = value
            if restore_composer:
                values[composer] = gr.update(
                    placeholder=tr("Ask a question, or attach documents"),
                    value=session.drafts.get(session.key, Draft()).payload(),
                    interactive=conversation.get("status", "active") == "active",
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

        def initialise(
            session: Session, requested: str, mode: str, language: str
        ) -> dict[Any, Any]:
            """Restore the addressable chat when the page establishes its Gradio session."""
            session.language = language if language in {"de", "en"} else "en"
            result = perform(session, None, lambda: controller.initialise(session, requested), True)
            result[language_control] = gr.update(value=session.language)
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
            session: Session, payload: dict[str, Any] | None, event: gr.EventData
        ) -> dict[Any, Any]:
            selected = str(event.chat_id)
            if event.action != "select":
                session.remember(payload)
                item = next(
                    (item for item in session.summaries if item["conversation_id"] == selected),
                    None,
                )
                if item is None:
                    session.error = (
                        "This chat is no longer available. Refresh the conversation list."
                    )
                    return render(session)
                session.managed_id = selected
                session.error = ""
                session.managed_action = (
                    event.action if event.action in {"rename", "move", "delete"} else "rename"
                )
                session.managed_folders = sorted(
                    {item["folder"] for item in session.summaries if item.get("folder")},
                    key=str.casefold,
                )
                result = render(session)
                result.update(
                    {
                        manager_panel: gr.update(visible=True),
                        manager_context: escape(item["title"]),
                        manager_name: gr.update(value=item["title"]),
                        manager_folder: gr.update(
                            choices=[
                                (translate("No folder", session.language), "none"),
                                *(
                                    (folder, f"folder:{index}")
                                    for index, folder in enumerate(session.managed_folders)
                                ),
                                (translate("Create new folder", session.language), "new"),
                            ],
                            value=f"folder:{session.managed_folders.index(item['folder'])}"
                            if item.get("folder")
                            else "none",
                        ),
                        manager_new_folder: gr.update(value="", visible=False),
                        manager_confirm: False,
                        manager_notice: gr.update(value="", visible=False),
                    }
                )
                return result
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

        def working(session: Session) -> dict[Any, Any]:
            text = escape(translate("Creating a reply…", session.language))
            return {
                submission_status: gr.update(
                    value='<div class="response-pending" data-submitting="true" role="status" aria-live="polite" aria-atomic="true"><span class="thinking-dots" aria-hidden="true"><i></i><i></i><i></i></span><span>'
                    + text
                    + "</span></div>",
                    visible=True,
                ),
                error: gr.update(visible=False),
            }

        def submit(session: Session, payload: dict[str, Any] | None) -> Iterator[dict[Any, Any]]:
            session.remember(payload)
            if payload and (str(payload.get("text") or "").strip() or payload.get("files")):
                yield working(session)
            yield perform(session, payload, lambda: controller.submit(session, payload), True)

        def retry_submission(
            session: Session, payload: dict[str, Any] | None
        ) -> Iterator[dict[Any, Any]]:
            if session.key in session.pending:
                yield working(session)
            yield perform(session, payload, lambda: controller.retry(session), True)

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
                document_table: document_rows(
                    controller.visible_documents(session), session.language
                ),
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
                    search_results: source_details(sources, session.show_sources, session.language)
                    or translate("No shared-library excerpts were found.", session.language)
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
            language_control,
            manager_panel,
            manager_title,
            manager_name,
            manager_folder,
            manager_confirm,
            manager_notice,
            manager_context,
            manager_rename,
            manager_move,
            manager_removal,
            manager_save,
            manager_delete,
            manager_new_folder,
            submission_status,
            scope_notice,
        ]
        outputs = list(dict.fromkeys([*outputs, *localized]))
        options: dict[str, Any] = {
            "outputs": outputs,
            "api_visibility": "private",
            "concurrency_id": "workspace",
            "concurrency_limit": 1,
            "show_progress": "minimal",
        }
        demo.load(
            initialise,
            inputs=[state, requested_chat, appearance_control, language_control],
            js='(state) => {let mode="System",lang="en";try {mode=(localStorage.getItem("localrag-appearance")||"system");mode=mode.charAt(0).toUpperCase()+mode.slice(1);lang=localStorage.getItem("localrag-language")||(navigator.language.startsWith("de")?"de":"en")}catch{}return [state,new URL(window.location.href).searchParams.get("chat")||"",mode,lang]}',
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
        chats.click(select_chat, inputs=[state, composer], **options)

        def change_language(
            session: Session, payload: dict[str, Any] | None, language: str
        ) -> dict[Any, Any]:
            session.remember(payload)
            session.language = language if language in {"de", "en"} else "en"
            return render(session)

        language_control.input(
            change_language,
            inputs=[state, composer, language_control],
            js='(state,payload,language) => {try{localStorage.setItem("localrag-language",language)}catch{} return [state,payload,language]}',
            **options,
        )

        def save_managed(
            session: Session,
            payload: dict[str, Any] | None,
            name: str,
            folder: str | None,
            new_folder: str,
        ) -> dict[Any, Any]:
            def apply() -> None:
                item = next(
                    (
                        item
                        for item in session.summaries
                        if item["conversation_id"] == session.managed_id
                    ),
                    None,
                )
                if item is None:
                    raise BackendError(
                        "This chat is no longer available. Refresh the conversation list."
                    )
                if session.managed_action == "rename":
                    controller.manage_chat(session, name, item.get("folder", ""))
                    return
                if folder == "new":
                    destination = new_folder.strip()
                    if not destination:
                        raise BackendError("Enter a folder name.")
                elif folder == "none":
                    destination = ""
                else:
                    choices = {
                        f"folder:{index}": value
                        for index, value in enumerate(session.managed_folders)
                    }
                    if folder not in choices:
                        raise BackendError("Choose a destination folder.")
                    destination = choices[str(folder)]
                controller.manage_chat(session, item["title"], destination)

            result = perform(session, payload, apply)
            result[manager_panel] = gr.update(visible=bool(session.error))
            result[error] = gr.update(visible=False)
            return result

        def delete_managed(
            session: Session, payload: dict[str, Any] | None, confirmed: bool
        ) -> dict[Any, Any]:
            was_active = session.managed_id == session.active_id
            result = perform(
                session,
                payload,
                lambda: controller.delete_managed_chat(session, confirmed),
                was_active,
            )
            result[manager_panel] = gr.update(visible=bool(session.error))
            result[error] = gr.update(visible=False)
            return result

        manager_save.click(
            save_managed,
            inputs=[state, composer, manager_name, manager_folder, manager_new_folder],
            **options,
        )
        manager_folder.input(
            lambda choice: gr.update(visible=choice == "new"),
            inputs=manager_folder,
            outputs=manager_new_folder,
            queue=False,
            api_visibility="private",
        )
        manager_delete.click(delete_managed, inputs=[state, composer, manager_confirm], **options)

        def close_manager(session: Session) -> dict[Any, Any]:
            session.error = ""
            session.managed_id = None
            return {state: session, manager_panel: gr.update(visible=False)}

        manager_close.click(
            close_manager,
            inputs=state,
            outputs=[state, manager_panel],
            queue=False,
            api_visibility="private",
        )
        composer.submit(submit, inputs=[state, composer], trigger_mode="once", **options)
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
            retry_submission,
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

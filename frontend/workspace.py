"""Session-scoped workspace commands; durable records remain in the backend."""

import mimetypes
import os
import tempfile
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any
from uuid import uuid4

from api_client import BackendClient, BackendError

FILE_TYPES = [".pdf", ".docx", ".txt", ".md", ".markdown"]


@dataclass
class Draft:
    """An unsent question and temporary Gradio uploads belonging to one chat."""

    text: str = ""
    files: list[str] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        """Return the native multimodal input value without reading file contents."""
        return {"text": self.text, "files": self.files.copy()}


@dataclass
class Submission:
    """Retain the same request ID and only the uploads still awaiting success."""

    draft: Draft
    request_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass
class Session:
    """Isolated browser-session state; no business records are stored globally."""

    active_id: str | None = None
    requested_chat: str | None = None
    conversation: dict[str, Any] | None = None
    summaries: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    model: str = ""
    top_k: int = 5
    temperature: float = 0.2
    max_upload_bytes: int = 20 * 1024 * 1024
    show_sources: bool = True
    new_use_library: bool = False
    initialised: bool = False
    error: str = ""
    service_notice: str = ""
    chat_query: str = ""
    library_query: str = ""
    selected_document: str | None = None
    selected_attachment: str | None = None
    drafts: dict[str, Draft] = field(default_factory=dict)
    pending: dict[str, Submission] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Keep an unsaved composer separate from every durable conversation."""
        return self.active_id or "new"

    @property
    def use_library(self) -> bool:
        """Resolve evidence scope from the saved chat or the unsaved composer."""
        return bool(self.conversation["use_library"]) if self.conversation else self.new_use_library

    def remember(self, payload: dict[str, Any] | None) -> None:
        """Capture the live composer before an action can change conversations."""
        if self.key not in self.pending:
            self.drafts[self.key] = read_draft(payload)


def read_draft(payload: dict[str, Any] | None) -> Draft:
    """Normalise Gradio's preprocessed, text-and-files composer value."""
    value = payload or {}
    return Draft(str(value.get("text") or ""), [str(path) for path in value.get("files", [])])


def source_details(sources: list[dict[str, Any]], show_text: bool) -> str:
    """Escape evidence snapshots before adding a compact, accessible disclosure."""
    if not sources:
        return ""
    entries = []
    for index, source in enumerate(sources, 1):
        label = f"[{source.get('source_id') or index}] {source['filename']}"
        if source.get("page"):
            label += f" - page {source['page']}"
        location = source.get("section") or f"Chunk {source['chunk_index'] + 1}"
        entries.append(
            f"<p><strong>{escape(label)}</strong><br>{escape(location)} - similarity {source['score']:.3f}</p>"
        )
        if show_text:
            entries.append(f"<pre>{escape(source['text'])}</pre>")
    return f"\n\n<details><summary>Sources ({len(sources)})</summary>{''.join(entries)}</details>"


def transcript(session: Session) -> list[dict[str, str]]:
    """Present saved prose with its original evidence, never a recomputed source list."""
    if not session.conversation:
        return []
    return [
        {
            "role": message["role"],
            "content": message["content"]
            + source_details(message.get("sources", []), session.show_sources),
        }
        for message in session.conversation["messages"]
    ]


def document_rows(documents: list[dict[str, Any]]) -> list[list[str | int]]:
    """Keep document selection aligned with the visible, deterministic row order."""
    return [
        [
            item["filename"],
            f"{item['size_bytes'] / 1024:.1f} KiB"
            if item["size_bytes"] >= 1024
            else f"{item['size_bytes']} B",
            item["chunk_count"],
            item["status"],
            item.get("error") or "",
        ]
        for item in documents
    ]


class Workspace:
    """Coordinate HTTP operations without embedding retrieval or generation logic."""

    def __init__(
        self, client: BackendClient | None = None, upload_root: Path | None = None
    ) -> None:
        self.client = client or BackendClient()
        self.upload_root = (
            upload_root
            or Path(os.environ.get("GRADIO_TEMP_DIR", str(Path(tempfile.gettempdir()) / "gradio")))
        ).resolve()

    def initialise(self, session: Session, requested_chat: str | None = None) -> None:
        """Restore records first, allowing saved chats to remain useful during model outages."""
        session.error = ""
        if requested_chat is not None:
            session.requested_chat = requested_chat
        self.refresh(session)
        try:
            data = self.client.models()
            session.models = data["models"]
            defaults = data["defaults"]
            session.max_upload_bytes = defaults["max_upload_bytes"]
            if not session.initialised:
                session.top_k = defaults["top_k"]
                session.temperature = defaults["temperature"]
            if session.model not in session.models:
                preferred = data.get("default_model")
                session.model = (
                    preferred if preferred in session.models else next(iter(session.models), "")
                )
            session.service_notice = (
                "" if session.models else "No installed local chat models are available."
            )
        except BackendError as error:
            session.service_notice = str(error)
        session.initialised = True
        requested = session.requested_chat
        if (
            session.active_id is None
            and requested
            and requested in {item["conversation_id"] for item in session.summaries}
        ):
            self.select(session, requested, None)

    def refresh(self, session: Session) -> None:
        """Read current backend records while preserving drafts and unfinished requests."""
        session.summaries = self.client.conversations()
        session.documents = self.client.documents()
        if session.active_id:
            if session.active_id not in {item["conversation_id"] for item in session.summaries}:
                session.active_id = None
                session.conversation = None
                session.attachments = []
            else:
                session.conversation = self.client.conversation(session.active_id)
                session.attachments = self.client.attachments(session.active_id)

    def select(
        self, session: Session, conversation_id: str, payload: dict[str, Any] | None
    ) -> None:
        """Switch explicitly to a listed chat, retaining the outgoing unsent draft."""
        if conversation_id not in {item["conversation_id"] for item in session.summaries}:
            raise BackendError("This chat is no longer available. Refresh the conversation list.")
        session.remember(payload)
        conversation = self.client.conversation(conversation_id)
        attachments = self.client.attachments(conversation_id)
        session.active_id = conversation_id
        session.requested_chat = conversation_id
        session.conversation = conversation
        session.attachments = attachments
        session.selected_attachment = None
        session.error = ""

    def new(self, session: Session, payload: dict[str, Any] | None) -> None:
        """Create a durable chat without altering any existing conversation."""
        session.remember(payload)
        conversation = self.client.create_conversation(
            session.model, session.top_k, session.temperature
        )
        if session.new_use_library:
            conversation = self.client.update_conversation(
                conversation["conversation_id"], use_library=True
            )
        session.active_id = conversation["conversation_id"]
        session.requested_chat = session.active_id
        session.conversation = conversation
        session.attachments = []
        session.selected_attachment = None
        session.new_use_library = False
        session.drafts.pop("new", None)
        session.error = ""
        self.refresh(session)

    def validate(self, session: Session, draft: Draft) -> None:
        """Reject unsupported, oversized or non-upload paths before creating records."""
        if len(draft.text) > 8000:
            raise BackendError("Questions may contain up to 8,000 characters.")
        for filename in draft.files:
            path = Path(filename).resolve()
            if not path.is_relative_to(self.upload_root) or not path.is_file():
                raise BackendError("The temporary upload is unavailable. Attach the file again.")
            if path.suffix.lower() not in FILE_TYPES:
                raise BackendError("Use PDF, DOCX, UTF-8 text or Markdown files.")
            if path.stat().st_size > session.max_upload_bytes:
                raise BackendError("An attachment exceeds the backend upload limit.")

    def submit(self, session: Session, payload: dict[str, Any] | None) -> None:
        """Accept text, files or both, and keep a recoverable submission on failure."""
        draft = read_draft(payload)
        if not draft.text.strip() and not draft.files:
            return
        if session.key in session.pending:
            raise BackendError(
                "Retry or discard the unfinished submission before sending another question."
            )
        self.validate(session, draft)
        if not session.active_id:
            self.new(session, payload)
        if session.conversation and session.conversation["status"] != "active":
            raise BackendError("This conversation is awaiting deletion.")
        session.drafts[session.key] = Draft(draft.text, draft.files.copy())
        session.pending[session.key] = Submission(draft)
        self.retry(session)

    def retry(self, session: Session) -> None:
        """Resume remaining uploads and reuse the message's idempotency key."""
        if not session.active_id or session.active_id not in session.pending:
            return
        pending = session.pending[session.active_id]
        while pending.draft.files:
            path = Path(pending.draft.files[0])
            self.validate(session, Draft(files=[str(path)]))
            self.client.upload_attachment(
                session.active_id,
                path.name,
                path.read_bytes(),
                mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            )
            pending.draft.files.pop(0)
        if pending.draft.text.strip():
            self.client.send_message(session.active_id, pending.draft.text, pending.request_id)
        del session.pending[session.active_id]
        session.drafts.pop(session.active_id, None)
        session.error = ""
        self.refresh(session)

    def discard(self, session: Session) -> None:
        """Discard only the selected chat's transient failed request."""
        session.pending.pop(session.key, None)
        session.drafts.pop(session.key, None)
        session.error = ""

    def toggle_library(self, session: Session) -> None:
        """Persist evidence opt-in only on the selected conversation."""
        if session.active_id:
            session.conversation = self.client.update_conversation(
                session.active_id, use_library=not session.use_library
            )
        else:
            session.new_use_library = not session.new_use_library

    def save_settings(
        self, session: Session, title: str, model: str | None, top_k: int, temperature: float
    ) -> None:
        """Keep a saved chat's settings independent from new-chat defaults."""
        if not 1 <= top_k <= 20 or not 0 <= temperature <= 1:
            raise BackendError("Choose valid retrieval and generation settings.")
        if session.active_id:
            fields: dict[str, Any] = {"title": title, "top_k": top_k, "temperature": temperature}
            if model:
                fields["model"] = model
            session.conversation = self.client.update_conversation(session.active_id, **fields)
            self.refresh(session)
        else:
            session.model = model or ""
            session.top_k, session.temperature = top_k, temperature

    def delete_chat(self, session: Session, confirmed: bool) -> None:
        """Require explicit confirmation before removing a chat and private originals."""
        if not confirmed or not session.active_id:
            raise BackendError(
                "Confirm that this chat and its unshared private files should be deleted."
            )
        removed = session.active_id
        self.client.delete_conversation(removed)
        session.pending.pop(removed, None)
        session.drafts.pop(removed, None)
        session.active_id = None
        session.requested_chat = None
        session.conversation = None
        session.attachments = []
        session.selected_attachment = None
        session.error = ""
        self.refresh(session)

    def visible_documents(self, session: Session) -> list[dict[str, Any]]:
        """Apply the same filter to the library table and its selection mapping."""
        return [
            item
            for item in session.documents
            if session.library_query.casefold() in item["filename"].casefold()
        ]

    def upload_library(self, session: Session, files: list[str] | None) -> None:
        """Index shared originals through the existing backend upload endpoint."""
        draft = Draft(files=files or [])
        self.validate(session, draft)
        for filename in draft.files:
            path = Path(filename)
            self.client.upload(
                path.name,
                path.read_bytes(),
                mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            )
        self.refresh(session)

    def delete_document(self, session: Session, confirmed: bool) -> None:
        """Delete only the explicitly selected library record, never a row offset."""
        if not confirmed or session.selected_document not in {
            item["document_id"] for item in session.documents
        }:
            raise BackendError("Select a library document and confirm its deletion.")
        self.client.delete(str(session.selected_document))
        session.selected_document = None
        self.refresh(session)

    def detach(self, session: Session, confirmed: bool) -> None:
        """Bind attachment removal to both the selected chat and a current document ID."""
        if (
            not confirmed
            or not session.active_id
            or session.selected_attachment
            not in {item["document_id"] for item in session.attachments}
        ):
            raise BackendError("Select a chat attachment and confirm its removal.")
        self.client.detach(session.active_id, str(session.selected_attachment))
        session.selected_attachment = None
        self.refresh(session)

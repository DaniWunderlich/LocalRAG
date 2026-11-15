# Changelog

## Unreleased

- Keep healthy chats and startup recovery available when a saved chat record is corrupt or unreadable; retain damaged originals, log only record identifiers, and block unsafe private-file cleanup until all references can be checked.
- Apply `MAX_UPLOAD_BYTES` consistently to Gradio ingress and backend validation in Compose, and show the actual backend limit in German and English.

## v0.3.0 — 2026-11-13

- Send chat messages with Enter and insert newlines with Shift+Enter, preserving input composition and preventing repeated-key submissions.
- Show an animated response indicator above the composer while submitting, retain input focus after Enter or the submit icon, and keep questions available for retry after a failure. Respect deliberate focus changes and reduced-motion preferences.
- Answer general questions with the selected local LLM when no documents are selected, retaining chat history and switching automatically to grounded answers when documents are included.
- Show general-chat guidance and localize the standard no-context response for unsupported document questions.

## v0.2.0 — 2026-11-12

### Added

- German and English interface selection using flag icons, remembered by the browser.
- Persistent chat folders with a compact destination picker, folder creation and removal from folders.
- Per-chat sidebar menus and separate dialogs for renaming, moving and confirmed deletion.
- Isolated browser checks for chat management, dialog geometry and scrolling at desktop, mobile and 1.25 device scale.

### Changed

- Replaced the Streamlit frontend with Gradio, retaining the local FastAPI, Qdrant and Ollama architecture.
- Retained addressable saved chats, private attachments, explicit shared-library opt-in, source disclosures, independent drafts and idempotent retries.
- Replaced appearance text buttons with sun, moon and monitor icons for Light, Dark and System.
- Used complete selection borders for chats, appearance icons and language flags, with visible keyboard focus.
- Moved sidebar action menus into a floating layer so they remain visible without adding sidebar overflow.

### Fixed

- Removed the contrasting sidebar search box border.
- Corrected dialog layering, composer icon alignment and cached library icons.
- Let Library and Settings panels grow with their content to prevent clipped headings and upload controls.
- Removed overlapping folder dropdown elements and unrelated actions from the move dialog.

### Upgrade

Rebuild frontend and backend together, preserving the existing volumes and Qdrant service:

```powershell
docker compose up -d --build --no-deps --wait backend frontend
```

Existing chats, documents, evidence snapshots and vectors remain usable. Older
chat records load without a folder; no conversion or reindexing is required.
The browser address remains `http://localhost:8501` unless configured otherwise.
The backend package and API metadata now report 0.2.0, matching the frontend.

## v0.1.0 — 2026-11-10

Initial release with Streamlit, local document ingestion and retrieval,
persistent conversations, private attachments, shared-library opt-in and
Light, Dark and System appearances.

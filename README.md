# Local RAG

A small, entirely local application for asking questions about your own documents.
Gradio provides the browser interface, FastAPI coordinates ingestion and RAG,
Qdrant stores document vectors and excerpts, and an existing Ollama instance
provides embeddings and chat completions. Documents and questions stay within
your infrastructure. No cloud AI service or agent framework is required.

Current release: **v0.3.0**. See [CHANGELOG.md](CHANGELOG.md) for release notes.

## Current functionality

Ask general questions directly to an installed local model without attaching a
document, or include documents for answers grounded in your files.

Upload PDF, DOCX, UTF-8 text and Markdown; inspect processing status; search
excerpts independently of generation; ask document questions; inspect the exact
sources supplied to the model; and delete originals together with their vectors.
Uploads are indexed synchronously. Duplicate content is detected using SHA-256.
Re-uploading a failed document retries its existing record.

Multiple independent chats are saved locally, including transcripts, evidence
snapshots, attachment links, model choice and generation settings. Create,
switch, search, rename and delete chats from the conversation workspace.
Each sidebar chat has a three-dot menu for renaming, moving to a folder and
deleting. Each action opens its own compact dialog. To move a chat, select an
existing destination or **Create new folder** and enter its name; **No folder** removes
the grouping. Folder assignments are saved with the chat, and folders can be
collapsed in the sidebar. Deletion requires confirmation and retains the
existing cleanup rules for shared and private documents. Managing another
chat preserves the open conversation and its unsent draft.
The selected chat has a complete accent border. Its menu floats below the
three-dot button in the browser's top layer, so opening it does not add sidebar
overflow or shift other chats. Near the screen's lower edge it opens upward
to keep every action visible. Appearance and language selections also use a
complete border; keyboard focus is drawn inside the icon without clipped edges.
Recent turns are included within a bounded history budget to interpret
follow-up questions; document-based answers still rely on the current source excerpts.

Attach PDF, DOCX, TXT or Markdown directly to the chat composer, with or without
a question. Attachments are private to that conversation. Switch on **Include
library** to also search deliberately shared library documents. Identical files
are stored and indexed once, while their conversation links remain separate.
Deleting a chat removes its unshared private originals and vectors, and keeps
documents still used by another chat or the shared library.

The pinned composer keeps chat controls within reach throughout a long
conversation. Two icon buttons sit immediately to the left of the file-upload
plus: settings opens a dialog for model choice, chat naming and generation
settings; the library icon directly includes or excludes shared documents.
The enabled library icon is highlighted and carries a check mark. Its label and
tooltip also explain the current action. A round down-arrow appears above the
composer when later messages are out of view; select it to return to the latest
message. Reduced-motion preferences are respected. Clicking the text field
keeps its neutral border.

Press **Enter** to send a message; **Shift+Enter** inserts a newline. The composer
shows an animated response indicator above the composer while a submission runs and retains a failed question
for retry. Empty submissions and Enter used to confirm input composition do not
send a message. Sending with Enter or the submit icon keeps focus in the text
field. It remains focusable and read-only while waiting, then becomes editable
when the answer arrives. Deliberately moving focus to another control is
respected. The indicator also respects reduced-motion preferences.

Without selected documents, questions go directly to the chosen local LLM for
general answers, using this chat's bounded conversation history. No document
sources are shown for these answers. Attach a file or include shared-library
documents to switch automatically to document-based answers. When selected
documents provide no usable excerpts, the application still returns a localized
context notice rather than filling gaps with general knowledge. Private files
from other chats remain excluded in both modes.

Use the sun, moon and monitor icons at the top right to choose **Light**, **Dark** or **System**.
The browser remembers this preference across pages and reloads. Both appearances
use the reading-desk palette throughout the chat, library, forms and dialogs.
This preference is separate from saved chat settings.
The adjacent German and British flag icons select German or English interface
text. The browser remembers the language, initially following its German or
English preference (other browser languages use English). User messages,
answers, filenames and saved chat names keep their original text. The sidebar
search uses the rail background without a contrasting box or border.

The v0.1.0 interface imported transcripts from the original session-only UI
into saved chats. Gradio restores these backend records through the same API.
Successful message
submissions have stable request IDs, so retrying a timed-out request does not
duplicate a committed exchange. Failed submissions retain a retryable browser
draft. Browser reading preferences and new-chat defaults remain session-only.

OCR, authentication, hybrid search, reranking, agents, multiple backend replicas
and Kubernetes manifests are outside the initial scope.

## Quick start

You need Docker Compose, a running Ollama instance reachable from Docker, and
locally installed embedding and completion models. Installation and image builds
require access to package registries; normal document processing uses local
services only.

From the repository root, create `.env` if you do not already have one:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

The example keeps the specification's initial embedding model,
`embeddinggemma:300m`. Set `OLLAMA_EMBEDDING_MODEL` to your installed model.
The current local configuration uses `qwen3-embedding:4b`, selected for this
workspace. The application never downloads models automatically.

Set `OLLAMA_BASE_URL=http://host.docker.internal:11434` for Ollama on this
computer. For another machine, use its local network URL. The Compose host
gateway entry also supports Linux Docker; Ollama must listen on an interface
reachable from the containers. Check local firewall and Ollama listener settings
if readiness fails.

The example defines `COMPOSE_FILE=deploy/compose.yaml` and
`COMPOSE_PROJECT_NAME=localrag`, allowing these commands from the repository root:

```powershell
docker compose up -d --build --wait
docker compose ps
docker compose logs -f
```

For an existing `.env` without those Compose variables, use the explicit form:

```powershell
docker compose --env-file .env -f deploy/compose.yaml -p localrag up -d --build --wait
```

Open [Local RAG](http://localhost:8501), choose a local chat model and attach
a document using the paperclip in the composer. Send the file on its own or
include a question. Return to saved threads in the conversation rail. Expand
**Sources** to inspect the evidence actually supplied with each answer.

**Library** manages documents that may be shared across chats. A new chat does
not use these until **Include library** is enabled. The independent search API
remains available for retrieval diagnostics.

Only the Gradio frontend is published, bound to `127.0.0.1:8501`. The backend and Qdrant
remain inside the Compose network. This initial version has no authentication;
keep it within a trusted local environment.

Stop the application while preserving its documents:

```powershell
docker compose down
```

Rebuild after source changes using `docker compose up -d --build --wait`.
A plain restart does not rebuild application code.

## Architecture and layout

| Location | Responsibility |
| --- | --- |
| `backend/src/rag/api/` | Validated document, search, chat and system endpoints |
| `backend/src/rag/ingestion/` | Upload validation, parsing, chunking and indexing |
| `backend/src/rag/retrieval/` | Query embedding, search and bounded context assembly |
| `backend/src/rag/generation/` | Grounded prompts and source mapping |
| `backend/src/rag/providers/` | Ollama HTTP and Qdrant adapters |
| `backend/src/rag/storage/` | Original files and atomic JSON metadata |
| `frontend/` | Conversation workspace, shared design tokens and backend HTTP client |
| `deploy/` | Compose deployment and source-mount development overrides |
| `backend/tests/`, `frontend/tests/` | Offline API, ingestion, provider, persistence and UI tests |
| `scripts/`, `eval/` | Real-service acceptance checks and a 16-question evaluation corpus |

The original [vision](docs/VISION.md) and [specification](docs/SPEC.md) are kept
as the initial baseline. The conversation workspace, persistent history and
per-chat document scope are subsequent requested extensions described here.

One backend process serialises document mutations, conversation writes and retrieval snapshots.
Originals are stored under internal UUIDs rather than uploaded filenames.
Document metadata is committed using a flushed temporary file and atomic
replacement. Only records with status `indexed` participate in retrieval.

Indexing writes bounded batches. If a batch fails, the backend attempts to
remove every point for that document and records a failed status. If Qdrant is
unavailable during cleanup, the document remains excluded from search. Retry
the upload or deletion once the service is available. Interrupted uploads are
marked failed on startup; interrupted deletions are retried.

## Models, context and sources

The collection's named-vector schema encodes both the embedding model name and
its Ollama digest. Dimensions are obtained from actual embedding responses.
Changing a model tag, replacing its underlying weights or changing vector
dimensions causes a compatibility error rather than mixing incompatible data.
Do not update an active model concurrently with indexing or retrieval.

Only installed models advertising completion capability are offered for chat.
Models identified as remote by Ollama metadata are rejected. Keep the Ollama
service itself configured for local operation.

Chunking estimates tokens using Unicode word runs of up to three characters
and individual punctuation marks, preserving page or section boundaries and
preferring paragraph, sentence and word endings. Overlap uses the same lexical
units. This deterministic heuristic works offline and is shared with context
assembly; it is not the exact tokeniser of every model or language.

Context assembly reserves room for instructions, the question, the requested
answer and an estimation margin within the model's reported context limit.
Only complete excerpts that fit are sent. Their labels correspond exactly to
the returned sources. A source list describes supplied evidence, and does not
certify the model's claims. Unknown numeric source labels are rejected.
Review answer quality on your actual documents and reduce budgets if a model's
tokenisation requires more room.

The real-service smoke test uses `qwen3-embedding:4b` and `granite3.3:8b`.
A first run with `llama3.2:3b` retrieved the correct excerpt but produced an
unnecessarily evasive answer and did not use the requested citation format.
Model choice therefore remains a quality decision, even when retrieval works.

## Configuration

Configuration is read from environment variables and validated at startup.
`.env.example` documents the common settings; `.env` is ignored by Git.

| Variable | Default | Meaning |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | Native: `http://localhost:11434`; Compose: host gateway | Existing Ollama service |
| `OLLAMA_CHAT_MODEL` | Empty | Optional backend default; otherwise select in the interface |
| `OLLAMA_EMBEDDING_MODEL` | `embeddinggemma:300m` | One compatible embedding model per active index |
| `OLLAMA_TIMEOUT_SECONDS` | `180` | Timeout for an individual Ollama request |
| `QDRANT_URL` | Native: `http://localhost:6333`; Compose: internal Qdrant | Vector service |
| `QDRANT_COLLECTION` | `rag_documents` | Active vector collection |
| `RAG_CHUNK_SIZE` / `RAG_CHUNK_OVERLAP` | `600` / `80` | Estimated lexical tokens; overlap may be zero |
| `RAG_TOP_K` | `5` | Maximum retrieved excerpts, range 1?20 |
| `RAG_TEMPERATURE` | `0.2` | Generation temperature, range 0?1 |
| `RAG_CONTEXT_TOKENS` | `4096` | Maximum estimated excerpt budget |
| `RAG_ANSWER_TOKENS` | `1024` | Reserved output tokens |
| `MAX_UPLOAD_BYTES` | `20971520` | Shared frontend/backend per-file limit, initially 20 MiB |
| `DOCUMENT_STORAGE_PATH` | Native: `data/documents`; Compose: persistent volume | Originals and register |
| `FRONTEND_PORT` | `8501` | Loopback browser port |
| `BACKEND_URL` | Native: `http://localhost:8000`; Compose: internal backend | Frontend HTTP destination |
| `BACKEND_TIMEOUT_SECONDS` | `600` | Timeout for synchronous frontend requests |

Compose passes `MAX_UPLOAD_BYTES` to both services. Gradio ingress, initial
workspace validation and the backend use this byte limit; the library displays
the backend-reported limit in either interface language. Restart both services
after changing it. For native development, set the same value in both process
environments. Large or complex documents can exceed synchronous request
timeouts; inspect their record before retrying.

## API and health

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST / GET | `/api/v1/documents` | Upload and index / list documents |
| GET / DELETE | `/api/v1/documents/{id}` | Inspect / completely remove a document |
| POST | `/api/v1/search` | Retrieve ranked excerpts and metadata |
| POST | `/api/v1/chat` | Generate an answer with the supplied context sources |
| GET / POST | `/api/v1/conversations` | List / create persistent chats |
| GET / PATCH / DELETE | `/api/v1/conversations/{id}` | Restore, rename, set folder, configure or delete a chat |
| GET / POST | `/api/v1/conversations/{id}/documents` | Inspect / upload private chat attachments |
| DELETE | `/api/v1/conversations/{id}/documents/{document_id}` | Detach a document and clean up unshared originals |
| POST | `/api/v1/conversations/{id}/messages` | Idempotent question with bounded chat history |
| POST | `/api/v1/conversations/import` | Preserve a pre-upgrade browser transcript |
| GET | `/api/v1/models` | Local completion models and UI defaults |
| GET | `/health/live` | Process liveness, independent of external services |
| GET | `/health/ready` | Storage, Ollama, embedding model and compatible index readiness |
| GET | `/docs` | FastAPI OpenAPI interface during native development |

Readiness returns HTTP 503 when dependencies or index compatibility fail.
Container health uses liveness so that dependency failures do not prevent the
interface from displaying useful errors. API errors omit upstream bodies,
request contents and sensitive connection details. Structured backend logs
record operation outcomes and durations without complete questions or excerpts.

## Persistence, backups and controlled reindexing

The `document_data` volume contains original files, `registry.json`, per-chat
records under `chats/` and any reindex registry backups. Back up chat records
together with the document register; they include message and evidence history. The `qdrant_data` volume contains vectors, payloads
and collection configuration. Both survive normal restarts and `down`.
Qdrant needs suitable local block storage rather than an ordinary NFS volume.

Unreadable chat records are omitted from navigation without blocking healthy
chats or startup recovery. The original record stays in place; opening it
returns a controlled `409 chat_record_unreadable`. Backend warnings identify
only the record filename and error type, without transcript content. Restore or
repair that record from backup. Private-file cleanup is blocked while references
in any chat record cannot be checked; this prevents deleting another chat's
attachments. Library documents retain their existing deletion rules.

Back up both volumes and the relevant configuration as a consistent set.
A Qdrant backup alone cannot restore the originals or complete document
register. Stop frontend and backend writes during backup and use a consistent
Qdrant snapshot or stop Qdrant before copying its storage.

To change the embedding model, stop frontend and backend, preserve a backup,
and rebuild into a fresh collection:

```powershell
docker compose stop frontend backend
docker compose run --rm --no-deps backend python -m rag.reindex --target-collection rag_documents_v2 --embedding-model qwen3-embedding:4b
```

Qdrant and Ollama must remain available. The command refuses the active
collection and any existing target. It stages a new register and only replaces
the active metadata after every document succeeds. It preserves the previous
collection and saves the previous register on success. A failed rebuild leaves
the original register available; the partially built target can be inspected
and removed separately.

After success, set `QDRANT_COLLECTION=rag_documents_v2` and the corresponding
`OLLAMA_EMBEDDING_MODEL` in `.env`, then run:

```powershell
docker compose up -d --force-recreate --wait
```

Do not run this maintenance command alongside an active backend. For rollback,
stop writes, restore the saved register and previous configuration, and use the
preserved previous collection.

## Development and checks

Python is pinned to **3.14.7**. Backend and frontend have independent `uv.lock`
files. The container build uses **uv 0.13.7** and **Qdrant 1.20.0**.
The backend baseline includes FastAPI 0.162.2, while the frontend pins Gradio
6.31.0. Shared dependencies include httpx 0.28.1,
qdrant-client 1.20.0, pypdf 7.0.0 and python-docx 1.2.0. Lockfiles contain the
complete, platform-aware dependency set.

```powershell
uv sync --project backend --locked
uv sync --project frontend --locked
uv run --project backend ruff check backend frontend scripts
uv run --project backend ruff format --check backend frontend scripts
uv run --project backend mypy --config-file backend/pyproject.toml backend/src
uv run --project frontend mypy --config-file frontend/pyproject.toml frontend
uv run --project backend pytest -c backend/pyproject.toml backend/tests --basetemp=.tmp/pytest-backend -q
```

Run the frontend tests from its own directory so its local modules are importable:

```powershell
Set-Location frontend
uv run pytest tests --basetemp=../.tmp/pytest-frontend -q
```

The backend tests use a real ephemeral in-memory Qdrant implementation and
mocked Ollama HTTP responses. They require no running LLM or external database.
The frontend tests exercise the session-scoped workspace commands against a
backend double and check the native Gradio application. Optional Playwright
tests exercise the actual UI against an isolated, seeded Compose stack.

For native backend development, configure `QDRANT_URL`,
`OLLAMA_BASE_URL=http://localhost:11434` and a local document path, then run
`uv run --project backend uvicorn rag.main:app --reload`.
For the frontend, change into `frontend/` and run
`uv run uvicorn app:app --host 127.0.0.1 --port 8501`. The native frontend health
endpoint is `/health/live`. The container listens internally on port 7860;
Compose retains the existing external port 8501, or your `FRONTEND_PORT` override.

For container development with source reload:

```powershell
docker compose --env-file .env -f deploy/compose.yaml -f deploy/compose.dev.yaml -p localrag up -d --build
```

## Isolated real-service acceptance

Use a separate project and browser port. Its volumes must contain only the
artificial test corpus. Ollama remains the existing local service.

```powershell
$env:FRONTEND_PORT = "18501"
docker compose --env-file .env -f deploy/compose.yaml -p localrag-acceptance up -d --build --wait
Get-Content -Raw scripts/acceptance.py | docker compose --env-file .env -f deploy/compose.yaml -p localrag-acceptance exec -T backend python - initialise
docker compose --env-file .env -f deploy/compose.yaml -p localrag-acceptance restart
docker compose --env-file .env -f deploy/compose.yaml -p localrag-acceptance up -d --wait
Get-Content -Raw scripts/acceptance.py | docker compose --env-file .env -f deploy/compose.yaml -p localrag-acceptance exec -T backend python - verify
Get-Content -Raw scripts/acceptance.py | docker compose --env-file .env -f deploy/compose.yaml -p localrag-acceptance exec -T backend python - cleanup
docker compose --env-file .env -f deploy/compose.yaml -p localrag-acceptance down --volumes
Remove-Item Env:FRONTEND_PORT
```

The final volume removal applies only to the disposable acceptance project.
The script defaults to the installed `granite3.3:8b` chat model; pass
`exec -e ACCEPTANCE_CHAT_MODEL=your-local-model -T backend ...` to change it.
See [the evaluation guide](eval/README.md) for the 16-question retrieval and
manual answer-quality baseline.

## Implementation status

The initial document-to-answer path is implemented and covered by offline tests
and real-service acceptance checks. Further quality work should use a larger
representative corpus before changing retrieval or chunking strategies.
The exact token count, answer quality and citation compliance remain
model-dependent. Kubernetes deployment and horizontal scaling require
separate work; the current JSON registry supports one backend instance.

## Conversation workspace validation

The interface uses a compact conversation rail, a bounded reading column,
inline attachments and progressively disclosed sources and chat options.
Paper, ink and evergreen colours, local system fonts and restrained borders
provide a consistent visual language without dashboard metrics or decorative
cards. The local design notes in `docs/DESIGN.md` are intentionally ignored
by Git.

Rendered screens were reviewed at 1440, 768 and 390 px, including the populated
conversation, a 14-chat navigation list, the mobile drawer and library upload
form. The review corrected the clearance below fixed navigation and strengthened
muted-text styling. Controls retain native labels and keyboard semantics, with
visible focus rules and reduced-motion support. This is not a full independent
WCAG conformance audit.

The offline automated suite has 81 backend tests and 23 frontend tests. It covers general chat and mode switching, folder persistence, compatibility with existing chat records, targeted chat management, localized navigation, private evidence isolation, explicit library opt-in,
shared-content deduplication, follow-up context, durable settings, safe deletion,
interrupted-operation recovery, idempotent sends, composer uploads, isolated
retry drafts, composer settings and import of the original session-only transcript.

For the additional real-service acceptance run, use the disposable
`localrag-design-review` project with `FRONTEND_PORT=18501`, and run
`scripts/acceptance_chats.py` inside its backend through the same stdin pipeline
as the initial acceptance script. Its phases are `initialise`, `verify` after
restarting the test containers, and `cleanup`. It checks two real grounded
turns using local Ollama, persistence of all 14 test chats, evidence isolation
and preservation of shared-library originals during chat deletion.

The Gradio migration retains the reading column, conversation rail, private
attachments, source disclosures, direct library icon, settings dialog and
jump-to-latest control. Appearance uses the matching light and dark palette
with a locally stored Light, Dark or System choice. Temporary uploads are
restricted to Gradio's upload cache and capped before backend ingestion.
Telemetry, public share tunnels, monitoring, MCP and server-side rendering are
disabled. The frontend serves local assets and system fonts.

## Gradio migration and browser acceptance

Version **0.2.0** replaces the Streamlit frontend from the published
v0.1.0 baseline. Existing API routes, document records, Qdrant configuration,
model compatibility and existing volumes are preserved. Conversation records
gain an optional folder field; older records load as ungrouped chats.
No reindexing or data conversion is required. The original vision and initial
specification describe the v0.1.0 stack; this frontend decision supersedes their
Streamlit references.

The new UI uses a Gradio `State` per browser session. It restores saved chats
through the backend and keeps the selected chat addressable through `?chat=...`.
Live drafts remain separate when switching chats. A failed submission retains
its original request ID and resumes only the remaining uploads. Drafts and
unfinished browser requests are temporary and do not survive a frontend restart;
committed messages and documents remain in the backend volume. Gradio's temporary
upload cache is cleaned periodically after 24 hours. Reattach expired uploads.

Update the frontend and backend together for persistent folder support,
preserving the existing volumes and Qdrant service:

```powershell
docker compose up -d --build --no-deps --wait backend frontend
```

Keep the original v0.1.0 checkout or frontend image available if you need to
restore that UI. Both frontends use the same saved-chat API and storage format.
Existing chat records without a folder load as ungrouped; no reindexing or
conversion is required.

Twenty-four additional browser tests exercise the composer and navigation with an isolated
in-memory backend and artificial chats, without Docker or Ollama. They cover
both appearances at 1440 and 390 px, language and appearance persistence,
renaming, folder creation/removal, confirmed deletion and independent drafts.
They also check uniform selection borders, keyboard focus and fully visible
menus without added sidebar overflow at desktop, mobile and 1.25 device scale,
including long chat lists.
The folder-dialog cases also check existing destinations, new-name validation,
cancellation and non-overlapping controls in both appearances at desktop,
mobile and 1.25 device scale:

```powershell
uv run --project frontend playwright install chromium
$env:LOCALRAG_UI_TESTS = "1"
uv run --project frontend pytest frontend/tests/test_navigation_browser.py --basetemp=.tmp/pytest-navigation -q
Remove-Item Env:LOCALRAG_UI_TESTS
```

For real-service and browser acceptance, create a disposable project containing
only artificial documents. Use the existing local Ollama service:

```powershell
$env:FRONTEND_PORT = "18501"
docker compose --env-file .env -f deploy/compose.yaml -p localrag-gradio-review up -d --build --wait
Get-Content -Raw scripts/acceptance_gradio.py | docker compose --env-file .env -f deploy/compose.yaml -p localrag-gradio-review exec -T frontend python - initialise
```

The controller acceptance checks real uploads, two grounded turns, an interrupted
response after commit, idempotent retry, private evidence isolation and distinct
unsent drafts. It prints the address of a seeded 24-message visual review chat.
Set `GRADIO_E2E_URL` to that complete address before running browser tests:

```powershell
uv run --project frontend playwright install chromium
$env:GRADIO_E2E_URL = "http://localhost:18501/?chat=ID_FROM_ACCEPTANCE_OUTPUT"
uv run --project frontend pytest frontend/tests/test_browser.py frontend/tests/test_ui_regressions.py --basetemp=.tmp/pytest-gradio-browser -q
```

The sixteen browser checks cover desktop, tablet and mobile widths (1440, 906,
768 and 390 px), icon alignment with multiline drafts and attachments, loaded
library icons after repeated toggles, modal layering above the open sidebar,
focus isolation, appearance changes, draft retention, source disclosures,
file-only uploads, per-chat drafts and the scroll control. Regression cases also
render at a device scale factor of 1.25 in light and dark appearances. Screenshots
are written under `.tmp/gradio-browser/` and `.tmp/gradio-ui-fixes/`. These tests
are skipped when the URL is unset. Use only the disposable test project: browser checks deliberately create
chat records and upload artificial files.

Restart the test containers and verify that the original saved records survive:

```powershell
docker compose --env-file .env -f deploy/compose.yaml -p localrag-gradio-review restart
docker compose --env-file .env -f deploy/compose.yaml -p localrag-gradio-review up -d --wait
Get-Content -Raw scripts/acceptance_gradio.py | docker compose --env-file .env -f deploy/compose.yaml -p localrag-gradio-review exec -T frontend python - verify
docker compose --env-file .env -f deploy/compose.yaml -p localrag-gradio-review down --volumes
Remove-Item Env:FRONTEND_PORT
Remove-Item Env:GRADIO_E2E_URL
```

Volume removal in this example applies exclusively to the disposable test
project. Preserve the normal `localrag` project's volumes throughout migration.

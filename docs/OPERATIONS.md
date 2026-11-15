# Configuration and operations

Run all commands from the repository root unless noted otherwise. Start with
[the README](../README.md) for installation and a tour of the interface.
The commands below work in PowerShell and Bash except where labelled.

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

The original [vision](VISION.md) and [specification](SPEC.md) are kept
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

## Development

Python is pinned to 3.14.7; the backend and frontend have independent lockfiles.
Install uv, then run the same commands on Windows or Linux:

```sh
uv sync --project backend --locked
uv sync --project frontend --locked
uv run --project backend ruff check backend frontend scripts
uv run --project backend ruff format --check backend frontend scripts
uv run --project backend mypy --config-file backend/pyproject.toml backend/src
uv run --project frontend mypy --config-file frontend/pyproject.toml frontend
uv run --project backend pytest -c backend/pyproject.toml backend/tests --basetemp=.tmp/pytest-backend -q
cd frontend
uv run pytest tests --basetemp=../.tmp/pytest-frontend -q
cd ..
```

Offline tests use an ephemeral in-memory Qdrant implementation and mocked Ollama
responses. To include the isolated native Playwright checks, install Chromium:

```sh
uv run --project frontend playwright install chromium
```

On Linux, Chromium may also need system packages; use
`uv run --project frontend playwright install --with-deps chromium` where you
have permission to install them.

PowerShell:

```powershell
$env:LOCALRAG_UI_TESTS = "1"
cd frontend
uv run pytest tests/test_navigation_browser.py -q
cd ..
Remove-Item Env:LOCALRAG_UI_TESTS
```

Bash:

```bash
(cd frontend && LOCALRAG_UI_TESTS=1 uv run pytest tests/test_navigation_browser.py -q)
```

For native development, supply environment variables explicitly; the frontend
reads its process environment, not the root `.env` automatically. Run Qdrant
separately and configure `QDRANT_URL`, `DOCUMENT_STORAGE_PATH` and
`OLLAMA_BASE_URL` for the backend, plus `BACKEND_URL` for the frontend. Both
processes must receive the same `MAX_UPLOAD_BYTES`.

```sh
uv run --project backend uvicorn rag.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```sh
cd frontend
uv run uvicorn app:app --host 127.0.0.1 --port 8501
```

For container development with source reload:

```sh
docker compose --env-file .env -f deploy/compose.yaml -f deploy/compose.dev.yaml -p localrag up -d --build
```

## Isolated real-service acceptance

These checks upload artificial documents, create chats and call local Ollama.
They assume installed `qwen3-embedding:4b` and `granite3.3:8b` models; set the
embedding model in the test environment accordingly. Use a separate project
and port. Never point these checks at your normal data.

PowerShell:

```powershell
$env:FRONTEND_PORT = "18501"
$env:OLLAMA_EMBEDDING_MODEL = "qwen3-embedding:4b"
docker compose --env-file .env -f deploy/compose.yaml -p localrag-gradio-review up -d --build --wait
Get-Content -Raw scripts/acceptance_gradio.py | docker compose --env-file .env -f deploy/compose.yaml -p localrag-gradio-review exec -T frontend python - initialise
```

Bash:

```bash
export FRONTEND_PORT=18501
export OLLAMA_EMBEDDING_MODEL=qwen3-embedding:4b
docker compose --env-file .env -f deploy/compose.yaml -p localrag-gradio-review up -d --build --wait
docker compose --env-file .env -f deploy/compose.yaml -p localrag-gradio-review exec -T frontend python - initialise < scripts/acceptance_gradio.py
```

The script prints a review URL with a saved chat ID. Set `GRADIO_E2E_URL` to that
complete address in your shell, then run the seeded browser checks:

```sh
cd frontend
uv run pytest tests/test_browser.py tests/test_ui_regressions.py -q
cd ..
```

After restarting the disposable stack, run the acceptance script again with
`verify` instead of `initialise`. It also verifies records after frontend
recreation. Remove only this test project's volumes when finished:

```sh
docker compose --env-file .env -f deploy/compose.yaml -p localrag-gradio-review down --volumes
```

Restore or unset `FRONTEND_PORT`, `OLLAMA_EMBEDDING_MODEL` and `GRADIO_E2E_URL`
in your shell afterward. Preserve the normal `localrag` volumes.

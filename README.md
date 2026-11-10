# Local RAG

A small, entirely local application for asking questions about your own documents.
Streamlit provides the browser interface, FastAPI coordinates ingestion and RAG,
Qdrant stores document vectors and excerpts, and an existing Ollama instance
provides embeddings and chat completions. Documents and questions stay within
your infrastructure. No cloud AI service or agent framework is required.

## Current functionality

Upload PDF, DOCX, UTF-8 text and Markdown; inspect processing status; search
excerpts independently of generation; ask document questions; inspect the exact
sources supplied to the model; and delete originals together with their vectors.
Uploads are indexed synchronously. Duplicate content is detected using SHA-256.
Re-uploading a failed document retries its existing record.

Chat preferences and the displayed conversation last for the current browser
session. Each backend question is independent: earlier conversation messages are
not included in the prompt. There is no persistent chat history.

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

Open [Local RAG](http://localhost:8501), upload a document on **Documents**,
select an installed chat model and ask a question. Expand a source to inspect
its excerpt, document location and similarity score. **Inspect document search**
lets you assess retrieval without generating an answer.

Only Streamlit is published, bound to `127.0.0.1:8501`. The backend and Qdrant
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
| `frontend/` | Streamlit pages and a shared backend HTTP client |
| `deploy/` | Compose deployment and source-mount development overrides |
| `backend/tests/`, `frontend/tests/` | Offline API, ingestion, provider, persistence and UI tests |
| `scripts/`, `eval/` | Real-service acceptance checks and a 16-question evaluation corpus |

The original [vision](docs/VISION.md) and [specification](docs/SPEC.md) remain
the source documents and are retained without rewriting their requirements.

One backend process serialises document mutations and retrieval snapshots.
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
| `MAX_UPLOAD_BYTES` | `20971520` | Backend limit, initially 20 MiB |
| `DOCUMENT_STORAGE_PATH` | Native: `data/documents`; Compose: persistent volume | Originals and register |
| `FRONTEND_PORT` | `8501` | Loopback browser port |
| `BACKEND_URL` | Native: `http://localhost:8000`; Compose: internal backend | Frontend HTTP destination |
| `BACKEND_TIMEOUT_SECONDS` | `600` | Timeout for synchronous frontend requests |

Streamlit also caps uploads at 20 MiB in `frontend/.streamlit/config.toml`.
Align that value if you deliberately increase the backend limit. Large or
complex documents can exceed synchronous request timeouts; inspect their
record before retrying.

## API and health

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST / GET | `/api/v1/documents` | Upload and index / list documents |
| GET / DELETE | `/api/v1/documents/{id}` | Inspect / completely remove a document |
| POST | `/api/v1/search` | Retrieve ranked excerpts and metadata |
| POST | `/api/v1/chat` | Generate an answer with the supplied context sources |
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

The `document_data` volume contains original files, `registry.json` and any
reindex registry backups. The `qdrant_data` volume contains vectors, payloads
and collection configuration. Both survive normal restarts and `down`.
Qdrant needs suitable local block storage rather than an ordinary NFS volume.

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
The resolved baseline includes FastAPI 0.162.2, Streamlit 1.67.0, httpx 0.28.1,
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
The frontend tests use Streamlit's application test runner and a backend double.

For native backend development, configure `QDRANT_URL`,
`OLLAMA_BASE_URL=http://localhost:11434` and a local document path, then run
`uv run --project backend uvicorn rag.main:app --reload`.
For the frontend, run `uv run --project frontend streamlit run frontend/app.py`.

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

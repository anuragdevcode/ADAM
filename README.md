# ADAM

*A.D.A.M. — Administrative Directive & Archival Memory.*

ADAM is a platform for turning approved Uttarakhand public records into a connected, queryable knowledge base — not a single assistant, but the infrastructure behind one. Connect your data and ADAM's ingestion pipelines take care of getting it into the database; choose which models power your workspace, local or API-based; and bring your organization on board with shared access for its members. ADAM runs local-first by default, with the option to connect hosted model APIs where that fits your deployment. Under the hood: a FastAPI backend, a Next.js web interface, PostgreSQL/pgvector persistence, document ingestion, OCR support, and local or API-based model and voice services.

## Technology Stack

### Backend & API

- **Language/runtime:** Python 3.10+ (Docker image built on `python:3.11-slim`)
- **Web framework:** FastAPI, served by Uvicorn (`standard` extras — uvloop, httptools)
- **Two API surfaces, deliberately separate:**
  - `/api/*` — the app-facing surface behind the Next.js UI, including the streaming chat endpoint (`POST /api/chat`, Server-Sent Events: `start` → `token` → `citations` → `banners`/`suggestions` → `done`)
  - `/v1/*` — a stricter external gateway contract (`chat`, `documents`, `search`, `ingestions`, `feedback`) with OpenAPI/JSON Schema validation, idempotency keys on writes, per-user rate limiting, and structured, non-disclosing error responses
- **Validation:** Pydantic v2
- **CLI:** Click (the `adam` command — serving, dev diagnostics, model management, review workflows)

### Data layer

- **Database Environments (Explicit Canonical Roles):**
  - **Native Local Development & Tests (Canonical: SQLite):** When running outside Docker (`adam serve`, CLI tools, pytest), ADAM defaults to local SQLite (`sqlite:///{BASE_DIR}/adam.db` or in-memory `sqlite:///:memory:` for pytest). This provides zero external daemon dependencies, fast startup, automated table creation, and missing-column schema migrations.
  - **Docker Compose, Staging & Production (Canonical: PostgreSQL 16 + pgvector):** In containerized multi-user environments, ADAM runs on `pgvector/pgvector:pg16` (`postgresql+psycopg://adam:change-me@postgres:5432/adam` configured via `DATABASE_URL`). PostgreSQL serves relational records, ACID transactions across concurrent workers, and vector similarity search without requiring an external vector database.
- **ORM/driver:** SQLAlchemy 2.0 with `sqlite3` for local dev/testing and `psycopg3` (binary) for PostgreSQL.
- **Retrieval:** hybrid search combining full-text/BM25 with pgvector similarity (or keyword/lexical ranking under SQLite), filtered by department and clearance-level ACLs *before* ranking; an optional cross-encoder reranker sits on top of that when benchmarks justify it.
- **Original document storage:** a local filesystem backend by default (`STORAGE_DIR`), built to swap to an S3-compatible backend for production without changing calling code.

### Model & agent layer

- **Local inference:** Ollama, via an `OllamaModelRuntime` — `qwen2.5:3b` is the default pulled model, with `qwen3:4b` (Apache-2.0) as the primary target and `qwen3:1.7b` kept as a low-memory fallback
- **Model governance:** a `ModelRegistry` tracks approved model artifacts (checksums, licenses, promotion gates); a `SingleModelLifecycleManager` enforces exactly one active model instance at a time — no silently running multiple LLMs concurrently
- **Graceful degradation:** a deterministic (non-LLM) runtime path takes over when no Ollama model is reachable, so the system degrades instead of failing outright
- **Agent orchestration (Canonical 7-Stage State Machine):**
  A bounded state machine governed by `AgentState` executes strictly once per query:
  1. `AUTHENTICATE`: Validates user identity and clearance level ceiling (`PUBLIC`, `INTERNAL`, `RESTRICTED`, `CONFIDENTIAL`).
  2. `CLASSIFY_REQUEST`: Extracts administrative filters (department, GO number, doc type) and evaluates jurisdiction.
  3. `RETRIEVE`: Executes exactly one authorized hybrid retrieval pass across repository records.
  4. `EVIDENCE_CURRENCY_CHECKS`: Assembles evidence packet and checks statutory currency against superseding amendments.
  5. `GENERATE_OR_ABSTAIN`: Synthesizes cited response or abstains if insufficient records exist (enforcing temperature 0–0.2).
  6. `VALIDATE_CITATIONS`: Audits and verifies all claim citations against the evidence packet.
  7. `AUDIT`: Writes an immutable, redacted audit record to the database.
  - **Terminal States:** `COMPLETED` (successful response), `ABSTAINED` (governed refusal/abstention), or `FAILED` (pipeline error/clearance denial).
  - **Whitelisted Read-Only Tools (`AgentToolName`):** `search`, `open_cited_source`, and `list_authorised_collections`. No arbitrary web browsing, emailing, or database write tools are available to the model.
- **Hosted API models:** supported as an alternative or addition to local Ollama models, for deployments that prefer or require it

### Document processing & OCR

- **PDF parsing:** PyMuPDF for born-digital text extraction, page rendering, and page-count verification
- **OCR:** Tesseract (with `tesseract-ocr-hin` for Devanagari) as the default engine; PaddleOCR supported for harder bilingual/layout-heavy scans, run as a queued worker rather than inline with chat requests
- **Image handling:** Pillow, with deskew/rotation/preprocessing gated behind quality checks rather than applied unconditionally
- **Quality gates:** automatic flags for low OCR confidence, low character yield, mixed-script uncertainty, tables, seals/signatures, handwritten content, and contradictory extracted-vs-OCR text — flagged pages require human review before they enter chunking
- **Precedent/supersession detection:** a bilingual (Hindi + English) parser that identifies when one order supersedes, amends, or continues another, feeding the "this GO may be outdated" warnings shown to officers

### Voice

- **Speech-to-text:** Groq-hosted Whisper large-v3 (`GROQ_API_KEY`, free tier, Hindi + English) when configured; otherwise Fast Whisper (`faster-whisper`) locally — an optional install (`pip install -e ".[voice]"`, bundled into the Docker image)
- **Text-to-speech:** ElevenLabs multilingual voices (`ELEVENLABS_API_KEY`, free tier) when configured; otherwise Piper
- Both fall back to a "null engine" that reports as unavailable via `GET /api/voice/status`, and the UI then uses the browser's Web Speech API — so voice works with no keys and no extra installs
- **Conversation loop:** the Next.js UI runs a hands-free listen → answer → speak → listen cycle with silence detection, tap-to-interrupt, and Markdown/citation stripping so only the answer prose is spoken (see [Voice conversation](#voice-conversation))

### Frontend

- **Framework:** Next.js 14 (React 18, TypeScript)
- **Styling:** Tailwind CSS
- **Icons:** lucide-react

### Security & governance

- Role/clearance-based access control (`X-User-Role`, `X-Clearance-Level` request headers) enforced at the retrieval layer, not just the UI
- Document-embedded prompt-injection detection and quarantining before content reaches the model
- Upload validation: magic-byte/format checks, executable (PE/ELF) rejection, suspicious embedded-PDF-action detection
- XSS detection and sanitization on both ingested and generated content
- Secrets and system-prompt redaction in logs and error responses
- Signed, tamper-evident audit manifests over the document inventory
- "Stealth" 404s — unauthorized requests get a not-found response rather than a message revealing that a restricted resource exists
- Session memory encrypted at rest, isolated per user, with TTL-based expiry and audited purge/delete

### Testing

pytest + pytest-cov, organized into layers: unit (metadata, hashing, chunk boundaries, ACL predicates), contract (OpenAPI conformance, auth/error non-disclosure), corpus (golden PDFs, Hindi/English, tables, corrupted files), RAG quality (gold question sets, no-answer/abstention cases, citation precision), security (RBAC, injection, upload attacks), and end-to-end integration/acceptance tests covering the full pipeline from PDF to cited chat answer.

### Deployment & infrastructure

- Docker Compose for local development (hot-reloading API and UI), with a separate `docker-compose.prod.yml` overlay for immutable production images
- Multi-stage Dockerfile (`python:3.11-slim` base; `development`/`production` targets)
- Resource profiles (`adam dev profile`) with defined RAM/disk budgets for three target environments: an 8GB MacBook Air pilot, a team dev server, and government production
- A cross-process "heavy worker" coordinator that mutually excludes resource-intensive tasks (OCR, model inference) so they don't compete for memory on constrained hardware
- `adam dev doctor` / `adam dev bootstrap` / `adam dev cache-clean` CLI diagnostics — local environment health checks, seeding an anonymized pilot corpus, and enforcing a disk cache ceiling

## Quick start with Docker

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- 8 GB RAM minimum; 16 GB is recommended when running local models.
- Optional: [Ollama](https://ollama.com/) for natural local-model answers.

Clone the repository and start the editable development stack:

```bash
git clone <YOUR-REPOSITORY-URL> adam
cd adam
docker compose up --build
```

Open:

- UI: <http://localhost:3000>
- API documentation: <http://localhost:8000/docs>
- API health check: <http://localhost:8000/api/health>

The first build downloads the Python, Node, Postgres, OCR, and voice dependencies. Subsequent starts use Docker cache and named volumes.

Stop the stack with `Ctrl+C`, then run:

```bash
docker compose down
```

This keeps the Postgres and application-storage volumes. To intentionally remove all local Compose data, run `docker compose down --volumes`; this deletes your local database and uploaded documents.

## Development workflow

The default `docker-compose.yml` is development-oriented:

- `./adam` and `./tests` are mounted into the API container; Uvicorn reloads Python changes.
- `./ui` is mounted into the UI container; Next.js hot reloads UI changes.
- Dependencies live in Docker images/named volumes, not in the checked-out source tree.
- PostgreSQL and document storage persist in named Docker volumes.

Useful commands:

```bash
make docker-up       # Start and build the stack
make docker-down     # Stop it, preserving local data volumes
make docker-logs     # Follow API and UI logs
make docker-build    # Rebuild images without cache
make docker-test     # Run backend tests inside the API image
docker compose ps    # Inspect container health
```

To run the production image configuration locally:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build
```

Production images do not mount application source code or the UI `node_modules` folder.

## Configuration

Copy the template only when you need to override defaults. Both Docker Compose and a native `adam serve` read `.env` from the repository root (values already set in the shell take precedence):

```bash
cp .env.example .env
```

`.env` is intentionally ignored by Git. Do not put credentials, access tokens, signing keys, model paths, or real connection strings in tracked files.

| Variable | Purpose | Development default |
| --- | --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Compose Postgres configuration | `adam`, `adam`, `adam_dev_password` |
| `DATABASE_URL` | Native API database URL | Compose provides a container URL |
| `STORAGE_DIR` | Uploaded documents and processing artifacts | `/app/.adam_storage` in Docker |
| `SIGNING_SECRET` | Manifest/audit signing secret | Development-only placeholder |
| `ADAM_PROFILE` | Resource profile | `DEV_SERVER` |
| `ADAM_MODEL_BACKEND` | Model runtime | `ollama` |
| `OLLAMA_HOST` | Ollama-compatible endpoint | `http://host.docker.internal:11434` |
| `API_PORT`, `UI_PORT`, `POSTGRES_PORT` | Host port overrides | `8000`, `3000`, `5432` |
| `ADAM_STT_PROVIDER` | Speech-to-text engine: `auto`, `groq`, `faster_whisper`, `none` | `auto` |
| `GROQ_API_KEY` | Free Groq key for hosted Whisper (Hindi + English) | empty → local Whisper / browser |
| `ADAM_TTS_PROVIDER` | Text-to-speech engine: `auto`, `elevenlabs`, `piper`, `none` | `auto` |
| `ELEVENLABS_API_KEY` | Free ElevenLabs key for natural multilingual voices | empty → browser voice |
| `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL_ID` | Voice and model used for spoken answers | `21m00Tcm4TlvDq8ikWAM`, `eleven_flash_v2_5` |

On Linux, `host.docker.internal` may not resolve to a host Ollama installation. Compose includes a host-gateway mapping on modern Docker versions; otherwise set `OLLAMA_HOST` in `.env` to your reachable Ollama address.

## Local models and large assets

Model weights, datasets, uploads, caches, and local databases are deliberately excluded from Git. They are covered by `.gitignore` and `.dockerignore`.

ADAM defaults to local models so a workspace can run fully offline, but model selection is meant to be a choice, not a constraint — a workspace can point at a hosted API-based model instead of, or alongside, a local one, depending on what that deployment needs.

For the default local chat model:

```bash
ollama pull qwen2.5:3b
```

With Docker running, ADAM will reach a host Ollama service through `OLLAMA_HOST`. The model selector only enables models that are actually installed. Never commit model files (`*.gguf`, `*.safetensors`, `*.onnx`, etc.); distribute them through Ollama, an artifact registry, or a separately mounted volume.

Fast Whisper is included in the API Docker image. On first transcription it may download its configured Whisper model into the container cache. For production, mount a managed cache/model volume and document its provenance instead of adding it to Git.

## Voice conversation

ADAM can be used entirely by voice: press **Voice** in the chat composer, ask a question out loud, and the answer is read back to you; ADAM then listens for your next question. Tap the mic while it is speaking to interrupt, and **End** to leave voice mode. The mic button next to it is hold-to-talk for single questions, and the speaker toggle reads answers aloud in text mode. Hindi and English are selectable in the composer.

Speech runs through pluggable engines chosen by `GET /api/voice/status`:

| Direction | Engine | Setup |
| --- | --- | --- |
| Speech → text | **Groq Whisper** (`whisper-large-v3-turbo`) | Free key from [console.groq.com/keys](https://console.groq.com/keys) → `GROQ_API_KEY` |
| Speech → text | faster-whisper (local CPU) | `pip install -e ".[voice]"` — used when no Groq key is set |
| Speech → text | Browser Web Speech API | Nothing — used when the server has neither (Chrome/Edge) |
| Text → speech | **ElevenLabs** (`eleven_flash_v2_5`, Hindi + English) | Free key from [elevenlabs.io](https://elevenlabs.io/app/settings/api-keys) → `ELEVENLABS_API_KEY` |
| Text → speech | Piper (local) | `piper` binary on `PATH` |
| Text → speech | Browser `speechSynthesis` | Nothing — used when the server has neither |

Put the keys in `.env` (never in tracked files) and restart the API; the composer's status line shows which engines are active. Both hosted tiers are free without a card: Groq bills by audio minutes at generous free limits, ElevenLabs gives ~10 minutes of speech per month, and ADAM only ever sends the cleaned answer prose (no citation metadata) to the TTS engine. Markdown and citation markers are stripped before speaking, so citations stay visual.

## Native development (without Docker)

Requires Python 3.10+ and Node.js 20+.

> **Database Note:** Native development uses local SQLite (`adam.db`) by default with zero setup. To connect to an external PostgreSQL database instead, export `DATABASE_URL=postgresql+psycopg://...` in your shell or `.env`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,voice]"
cd ui && npm ci && cd ..
adam serve --reload
```

In a second terminal:

```bash
cd ui
npm run dev
```

Run checks:

```bash
python3 -m pytest -q
cd ui && npm run build
```

## Backend ↔ Frontend Operational Transparency

ADAM incorporates a minimal, security-hardened operational transparency layer providing real-time visibility into the bounded administrative reasoning pipeline without leaking sensitive backend internals.

### Architectural Flow

```text
[Client / UI] ──(POST /api/chat)──> [FastAPI Router] (assigns trace_id)
                                          │
                                          ├── Spawns AgentStateMachine in worker thread
                                          ▼
[Pipeline Stages] ────> [OperationalEventEmitter] (monotonic sequencing & stage durations)
  1. security.started / completed / denied
  2. query.parsed (safe intent & language)
  3. retrieval.started / completed (candidate counts)
  4. evidence.started / completed / insufficient
  5. currency.checked / warning
  6. model.loading / ready / failed
  7. generation.started / completed / answer.grounded / abstained
  8. execution.completed / failed
                                          │
                                          ▼
[PublicEventSerializer] ──(Zero-leakage boundary enforcement & whitelisting)
                                          │
                                          ▼
[SSE Chat Stream] ────(event: status)──> [Next.js ExecutionStatus Component]
                                          ├── Live animated progress indicators
                                          ├── Collapsed badge: "✓ Grounded in N official sources"
                                          └── Expandable governance audit timeline
```

### Event Taxonomy

| Event Type | Stage | Status | Description | Public Data Whitelist |
| :--- | :--- | :--- | :--- | :--- |
| `security.started` | `security` | `running` | Identity & clearance verification started | None |
| `security.completed` | `security` | `completed` | Security check passed | None |
| `security.denied` | `security` | `failed` | Clearance authorization rejected | None |
| `query.parsed` | `query` | `completed` | Request intent and jurisdiction classified | `query_language`, `is_high_risk`, `is_out_of_jurisdiction` |
| `retrieval.started` | `retrieval` | `running` | Hybrid search across public records initiated | None |
| `retrieval.completed` | `retrieval` | `completed` | Record candidates evaluated | `candidate_count`, `records_considered` |
| `evidence.started` | `evidence` | `running` | Material passage extraction and scoring | None |
| `evidence.completed` | `evidence` | `completed` | Qualifying evidentiary passages selected | `selected_count` |
| `evidence.insufficient` | `evidence` | `warning` | No qualifying records in repository | `selected_count: 0` |
| `currency.checked` | `currency` | `completed` | Statutory currency verified | `banner_count: 0` |
| `currency.warning` | `currency` | `warning` | Superseding amendments or notices found | `banner_count` |
| `model.loading` | `model` | `running` | Model runtime activation | `model_name` |
| `model.ready` | `model` | `completed` | Model inference engine ready | `model_name` |
| `model.failed` | `model` | `failed` | Model runtime activation error | `model_name` |
| `generation.started` | `generation` | `running` | Governed answer synthesis started | `model_name` |
| `generation.completed`| `generation` | `completed` | Answer synthesis finished | `model_name` |
| `answer.grounded` | `grounding` | `completed` | Answer verified with official citations | `citation_count` |
| `answer.abstained` | `grounding` | `warning` | Pipeline abstained due to lack of evidence | `citation_count: 0` |
| `execution.completed`| `execution` | `completed` | Overall execution finished | `citation_count`, `duration_ms` |
| `execution.failed` | `execution` | `failed` | Execution halted unexpectedly | None |

### Security & Sanitization Boundary

All operational events emitted to the UI boundary pass through `PublicEventSerializer`:
1. **Attribute Whitelist**: Only approved numerical counts and non-sensitive metadata (`candidate_count`, `selected_count`, `duration_ms`, `banner_count`, `citation_count`, `query_language`, `is_out_of_jurisdiction`, `is_high_risk`, `model_name`) are permitted in public payloads.
2. **Forbidden Internals**: Keys or values containing SQL queries, file paths, API keys, bearer tokens, system prompts, tracebacks, or clearance mechanics are automatically stripped and purged.
3. **Pattern Redaction**: Any file paths or potential key strings within human-readable status messages are masked using regex sanitizers (`[path]`, `[redacted]`).

### OpenTelemetry Alignment

Each internal `OperationalEvent` tracks:
- `trace_id` and `span_id`
- `parent_span_id`
- Monotonic `sequence`
- Timestamp and stage duration in milliseconds (`duration_ms`)

This architecture allows plugging an external OpenTelemetry or Langfuse exporter without altering core agent logic.

## Troubleshooting

**Port already in use** — stop the process using port 3000, 8000, or 5432, or override `UI_PORT`, `API_PORT`, or `POSTGRES_PORT` in `.env`.

**UI cannot reach the API** — run `docker compose ps`, then visit <http://localhost:8000/api/health>. In Docker, the UI proxies `/api/*` to the `api` service; do not point browser code at the internal hostname.

**Model remains disabled** — run `ollama list`, pull the exact requested tag, and wait up to 15 seconds for the UI model inventory refresh. Confirm `OLLAMA_HOST` is reachable from the API container.

**Voice input reports unavailable** — check `GET /api/voice/status`. With no `GROQ_API_KEY` the API needs Fast Whisper and FFmpeg (rebuild with `docker compose build --no-cache api` if an earlier image predates this setup); without either, the UI uses the browser's own recognition, which needs Chrome/Edge and microphone permission on `localhost` or HTTPS.

**Answers are not spoken / wrong voice** — with `ELEVENLABS_API_KEY` set, inspect `docker compose logs api` for 401/429 responses (bad key or monthly quota). Without a key the browser's installed voices are used; install a Hindi voice in the OS for `हिन्दी` output.

**Database reset needed** — use `docker compose down --volumes` only when you intentionally want to delete all local Postgres and application storage data.

## Git hygiene

Only source code, documentation, manifests, Docker configuration, and safe templates belong in Git. Before committing, review:

```bash
git status --ignored
git check-ignore -v .env adam.db .adam_storage/example-file
```

Keep `.env.example` current, but never commit a real `.env`, downloaded model, local database, upload, generated artifact, virtual environment, or IDE workspace file.
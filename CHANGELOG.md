# Changelog

All notable changes to **ADAM** (Automated Document and Analytics Machine) are documented in this file.

This project adheres to [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) conventions and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Phase 4] — Hygiene & Observability (H-Series) — 2026-10-01

### Added
- **H3** — `CHANGELOG.md` and `CONTRIBUTING.md` project documentation files.
- **H7** — `npm audit` and `tsc --noEmit` (TypeScript type-check) scripts to `ui/package.json`.
- **H7** — CI workflow `frontend-build` job now runs TypeScript type-check and `npm audit --audit-level=moderate` after build.
- **H7** — ESLint upgraded to `^9` in `ui/package.json` dev dependencies.
- **H8** — OpenTelemetry OTLP exporter support (optional `[otel]` extra in `pyproject.toml`). Configures SDK automatically when `OTEL_EXPORTER_OTLP_ENDPOINT` env var is present; gracefully skips if SDK is not installed.
- **H8** — `/api/metrics` Prometheus endpoint now enforces `ADMIN` or `AUDITOR` role (previously also permitted `OPERATOR`).

### Changed
- `pyproject.toml` — added optional dependency group `otel` for `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc`, `opentelemetry-instrumentation-fastapi`, and `opentelemetry-instrumentation-sqlalchemy`.
- `.gitignore` — added explicit exceptions for `CHANGELOG.md` and `CONTRIBUTING.md`.

---

## [Phase 3] — Evaluation & Model Bakeoff (E-Series) — commit `16e73c7`

### Added
- **E1** — Held-out evaluation harness with deterministic reproducible test sets across all seven government departments.
- **E4** — Model bakeoff framework supporting multi-model parallel evaluation (Gemini, Qwen, Llama families).
- Wilson 95% confidence-interval reporting on all benchmark metrics endpoints (`/api/audit/benchmarks`, `/api/audit/benchmarks/reference`).
- Empirical RAG benchmark metrics exposed via `/api/audit/metrics` with real query-level accuracy and citation quality scores.

### Changed
- Evaluation metrics now include `latency_p95_ms` and `citations_per_query` fields.
- `test_evaluation_metrics.py` added to CI acceptance suite.

---

## [Phase 2] — Data Layer & Retrieval Scaling (R-Series) — commit `d6cee4c`

### Added
- **R1** — Native `pgvector` HNSW index for sub-10 ms approximate nearest-neighbour search at scale.
- **R2** — Hybrid BM25 + dense-vector retrieval with reciprocal rank fusion (RRF).
- **R3** — Full Alembic migration suite; forward (`upgrade`) and rollback (`downgrade base`) tested in CI on PostgreSQL 16.
- **R4** — Document ingestion pipeline with Tesseract OCR (Hindi `hin` model), PyMuPDF extraction, and structured chunking.
- **R5** — Source provenance tracking and citation attachment at retrieval time.
- **R6** — Backup and disaster-recovery drill CLI command (`adam backup drill`), verified in CI.
- **E3** — Retrieval-quality evaluation hooks (MRR, NDCG) embedded in ingestion and evaluation pipelines.
- **S11** — Database-level encryption-at-rest advisory and connection-string secret scanning.

### Changed
- `DATABASE_URL` now supports both SQLite (dev) and `postgresql+psycopg` (production).
- `adam db upgrade` / `adam db downgrade` CLI commands wired to Alembic.

---

## [Phase 1] — Auth, Multi-User Model & Security Hardening — commit `30db445`

### Added
- JWT-based authentication with short-lived access tokens and secure `httpOnly` refresh-cookie rotation.
- Multi-user model: roles `ADMIN`, `OFFICER`, `RECORDS_OFFICER`, `OPERATOR`, `AUDITOR`, `REVIEWER`, `PUBLIC`.
- `require_roles` FastAPI dependency used on all non-public endpoints.
- Bcrypt password hashing with per-user salts.
- `seed_default_admin_if_empty` bootstrap to provision a safe initial admin on first boot.
- User management REST endpoints (`/api/users`, `/api/users/{id}`).
- Audit log model and `/api/audit` router tracking all privileged mutations.
- Rate-limit middleware (`RateLimitMiddleware`) with per-IP sliding window.
- `TraceIdMiddleware` attaching a `X-Trace-Id` header to every response.

### Changed
- All chat, document, ingestion, and search endpoints now require authenticated callers.
- `CORS_ORIGINS` read from environment; defaults to `localhost` only.

---

## [Phase 0] — Stop-Ship Security Hardening & Audit Remediations — commit `ef4b878`

### Added
- `SecurityHeadersMiddleware`: `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, `Content-Security-Policy`, and production `Strict-Transport-Security`.
- `SecretRedactor` utility to strip credentials from structured logs and API responses.
- `SECURITY.md` — coordinated-disclosure policy for responsible vulnerability reporting.
- `.env.example` — documented all required environment variables with safe placeholder values.
- `.dockerignore` — prevents secrets and local state from leaking into container images.
- Removed all hard-coded credentials and API keys from source tree.

### Changed
- `/docs`, `/redoc`, and `/openapi.json` endpoints disabled in production (`ADAM_ENV=production`).
- Structured JSON error responses on all HTTP error codes (no stack traces exposed).

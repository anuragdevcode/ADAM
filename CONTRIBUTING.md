# Contributing to ADAM

Thank you for your interest in contributing to **ADAM** (Automated Document and Analytics Machine) —
the Uttarakhand Public Records AI Assistant & Knowledge Engine.

ADAM is a government-sector open-source project. All contributions are subject to the project's
[LICENSE](LICENSE) and must comply with the security and governance standards described in
[SECURITY.md](SECURITY.md).

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Development Setup](#development-setup)
3. [Running Tests](#running-tests)
4. [Code Style](#code-style)
5. [Pull Request Process](#pull-request-process)
6. [Commit Message Convention](#commit-message-convention)
7. [Security Disclosure](#security-disclosure)

---

## Code of Conduct

All contributors are expected to maintain professional and respectful discourse. Harassment,
discrimination, or disruptive behaviour of any kind will not be tolerated. Maintainers reserve
the right to remove any contribution or ban any participant who violates these standards.

---

## Development Setup

### Prerequisites

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| Python | 3.10 | 3.12 recommended |
| Node.js | 20 LTS | for UI (`ui/`) |
| PostgreSQL | 15 + pgvector | for production/CI |
| Tesseract OCR | 5.x | with `hin` language pack |

### Backend

```bash
# 1. Clone the repository
git clone https://github.com/your-org/ADAM.git
cd ADAM

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install the package in editable mode with dev extras
pip install -e ".[dev]"

# 4. Copy the example environment file and populate secrets
cp .env.example .env
$EDITOR .env

# 5. Apply database migrations (SQLite is fine for local development)
adam db upgrade

# 6. Seed the default admin account (only on empty DB)
adam dev bootstrap

# 7. Start the API server with hot-reload
adam-api --reload   # or: uvicorn adam.api.app:app --reload
```

### Frontend (UI)

```bash
cd ui
npm ci
npm run dev
```

The UI dev server starts at `http://localhost:3000` and proxies API requests to `http://localhost:8000`.

### Optional: OpenTelemetry

To enable distributed tracing, install the optional `otel` extras and set the endpoint:

```bash
pip install -e ".[otel]"
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317   # gRPC OTLP collector
```

ADAM will auto-configure tracing on startup when the env var is present.

---

## Running Tests

All tests live in the `tests/` directory and use **pytest**.

```bash
# Run the full suite (quiet mode)
pytest -q

# Run with verbose output and coverage
pytest -v --cov=adam --cov-report=term-missing

# Run a specific test file
pytest tests/test_integration_acceptance.py -v

# Run only tests matching a keyword
pytest -k "auth" -v
```

### CI Test Groups

The CI pipeline (`ci.yml`) runs tests in three phases:

1. **Primary Acceptance** — `tests/test_integration_acceptance.py`
2. **Security & Contract** — `test_security_acceptance.py`, `test_contract_openapi.py`, `test_evaluation_metrics.py`
3. **Full Regression** — entire `tests/` directory

All three phases must pass before a PR can be merged.

---

## Code Style

ADAM uses [**Ruff**](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
# Lint
ruff check adam/ tests/

# Auto-fix safe issues
ruff check --fix adam/ tests/

# Format
ruff format adam/ tests/
```

Configuration is in `pyproject.toml` under `[tool.ruff]`.

### Key Style Rules

- **Line length**: 110 characters.
- **Imports**: `isort`-compatible; stdlib → third-party → local, each group separated by a blank line.
- **Type hints**: required for all public functions and methods; use `from __future__ import annotations` for forward references.
- **Docstrings**: Google-style; required for all public classes, methods, and FastAPI route handlers.
- **No `print()`**: use the standard `logging` module; pass a named logger (`logger = logging.getLogger(__name__)`).
- **No secrets in code**: all credentials, API keys, and tokens must come from environment variables or `.env` files.

### Frontend

The `ui/` directory uses:

```bash
npm run lint        # ESLint (Next.js config)
npm run typecheck   # tsc --noEmit (strict TypeScript)
npm run audit       # npm audit (dependency vulnerability scan)
```

---

## Pull Request Process

1. **Fork** the repository and create a feature branch from `main`:

   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Write or update tests** for every behaviour change. PRs that reduce test coverage will not be merged.

3. **Run the full test suite and linters locally** before pushing:

   ```bash
   ruff check adam/ tests/ && pytest -q
   cd ui && npm run typecheck && npm run lint
   ```

4. **Open a Pull Request** against the `main` branch. Fill in the PR template:
   - What problem does this solve?
   - How was it tested?
   - Are there any breaking changes?
   - Does it touch any security-sensitive code?

5. **CI must be green**. All three backend test phases and the frontend build/type-check/audit must pass.

6. **Code review**: at least **one maintainer approval** is required. Security-sensitive changes (auth, encryption, audit) require **two approvals**.

7. **Squash and merge** is the preferred merge strategy. The PR title becomes the merge commit message and must follow the [Conventional Commits](#commit-message-convention) specification.

### What We Look For

- Correctness and adequate test coverage.
- No regressions to existing acceptance tests.
- Adherence to the existing role-based access control (RBAC) model.
- No hard-coded secrets, credentials, or environment-specific values.
- Structured logging (no `print` statements).
- Minimal surface-area changes — prefer small, focused PRs.

---

## Commit Message Convention

ADAM uses [**Conventional Commits**](https://www.conventionalcommits.org/en/v1.0.0/).

### Format

```
<type>(<scope>): <short imperative summary>

[optional body — wrap at 72 chars]

[optional footer(s)]
```

### Types

| Type | When to use |
|------|-------------|
| `feat` | A new user-facing feature |
| `fix` | A bug fix |
| `docs` | Documentation only changes |
| `style` | Formatting, missing semi-colons, etc. (no logic change) |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `perf` | Performance improvement |
| `test` | Adding or correcting tests |
| `chore` | Maintenance tasks (CI, deps, tooling) |
| `security` | Security fix or hardening (use for sensitive patches) |
| `revert` | Reverts a previous commit |

### Scopes (common)

`api`, `auth`, `rag`, `db`, `ui`, `eval`, `ingestion`, `observability`, `ci`, `deps`, `hygiene`

### Examples

```
feat(auth): add TOTP two-factor authentication for ADMIN role

fix(rag): correct chunk overlap calculation causing duplicate citations

security(api): restrict /api/metrics to ADMIN and AUDITOR roles only

chore(ci): add npm audit and TypeScript typecheck to frontend-build job

docs: add CHANGELOG and CONTRIBUTING for Phase 4 hygiene

test(eval): add held-out benchmark for GAD department accuracy
```

### Breaking Changes

Append `!` after the type/scope and add a `BREAKING CHANGE:` footer:

```
feat(api)!: remove deprecated /api/v0 endpoints

BREAKING CHANGE: The /api/v0/* namespace has been removed. Migrate to /v1/*.
```

---

## Security Disclosure

**Do not file a public GitHub issue for security vulnerabilities.**

Please follow the responsible-disclosure process described in [SECURITY.md](SECURITY.md):

1. Email the security team at the address listed in `SECURITY.md` with a clear description of the vulnerability, steps to reproduce, and potential impact.
2. You will receive an acknowledgement within **72 hours** and a resolution timeline within **7 business days**.
3. We ask that you refrain from public disclosure until a patch is released and affected deployments have had reasonable time to upgrade.
4. Credit will be given in the release notes to reporters who follow this process, unless they prefer to remain anonymous.

Security fixes follow an expedited review process and may be merged with a single approver if the second approver is unavailable and the severity is Critical or High.

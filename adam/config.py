"""Configuration settings for ADAM."""

import os
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None, *, override: bool = False) -> int:
    """Load ``KEY=VALUE`` lines from a ``.env`` file into ``os.environ``.

    Docker Compose reads ``.env`` on its own; this makes a native ``adam serve``
    behave the same way. Variables already present in the environment win
    unless ``override`` is set, so Compose- or shell-provided values are never
    clobbered. Returns the number of variables applied.
    """
    path = path or BASE_DIR / ".env"
    if not path.is_file():
        return 0
    applied = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if not key or (key in os.environ and not override):
            continue
        os.environ[key] = value
        applied += 1
    return applied


if os.getenv("ADAM_SKIP_DOTENV", "").lower() not in ("1", "true", "yes"):
    load_dotenv()

# ── Database Configuration ──────────────────────────────────────────────────
# ADAM supports two database backends with distinct, explicit environmental roles:
#
# 1. Native Local Development & Testing (Canonical: SQLite)
#    - URI: sqlite:///{BASE_DIR}/adam.db (or in-memory sqlite:///:memory: for pytest)
#    - Zero external dependencies: no Docker or PostgreSQL daemon required.
#    - Automatic schema table creation and missing-column migration via SQLAlchemy.
#    - Enabled by default whenever `DATABASE_URL` is omitted.
#
# 2. Docker Compose, Staging & Production (Canonical: PostgreSQL 16 + pgvector)
#    - URI: postgresql+psycopg://adam:change-me@postgres:5432/adam
#    - Used in containerized deployments defined in docker-compose.yml and production.
#    - Provides multi-user concurrent transactions and pgvector similarity indexing.
#    - Configured explicitly via the `DATABASE_URL` environment variable.
def get_database_url() -> str:
    """Return the database connection URL based on the environment.

    Defaults to local SQLite (`adam.db`) for native development and tests unless
    `DATABASE_URL` is explicitly set (e.g., in Docker Compose or production).
    """
    return os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'adam.db'}")

DATABASE_URL = get_database_url()

# Storage configuration
def get_storage_dir() -> Path:
    return Path(os.getenv("STORAGE_DIR", str(BASE_DIR / ".adam_storage")))

STORAGE_DIR = get_storage_dir()

# Collector / Ingestion
COLLECTOR_VERSION = "0.1.0"
DEFAULT_USER_AGENT = (
    "ADAM-Uttarakhand-Public-Records-Collector/0.1.0 "
    "(+https://uk.gov.in; departmental-authorised-crawler)"
)

# Environment mode
ADAM_ENV = os.getenv("ADAM_ENV", os.getenv("ENV", "development")).lower()

KNOWN_INSECURE_SECRETS = {
    "adam-uk-gov-default-auth-secret-key-2026",
    "change-me",
    "secret",
    "placeholder",
    "default",
    "password",
    "admin",
}

def get_signing_secret() -> str:
    """Retrieve signing secret with mandatory production enforcement."""
    env = os.getenv("ADAM_ENV", os.getenv("ENV", "development")).lower()
    secret = os.getenv("SIGNING_SECRET", "").strip()
    if env in ("production", "prod"):
        if not secret or secret in KNOWN_INSECURE_SECRETS:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: "
                "SIGNING_SECRET must be set to a secure, unique string in production. "
                f"Current value is {'empty' if not secret else 'a known insecure placeholder'}."
            )
        return secret
    # Development / test default
    return secret or "adam-uk-gov-default-auth-secret-key-2026"

def validate_production_database_url(url: str) -> str:
    """Ensure production database URL does not use insecure default credentials."""
    env = os.getenv("ADAM_ENV", os.getenv("ENV", "development")).lower()
    if env in ("production", "prod"):
        if "change-me" in url or "adam_dev_password" in url:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: "
                "DATABASE_URL contains default placeholder password credentials ('change-me'). "
                "You must supply a secure password in production."
            )
    return url


def get_memory_encryption_key() -> str:
    """Retrieve conversation memory encryption key with production separation checks."""
    env = os.getenv("ADAM_ENV", os.getenv("ENV", "development")).lower()
    mem_key = os.getenv("MEMORY_ENCRYPTION_KEY", "").strip()
    signing_secret = os.getenv("SIGNING_SECRET", "").strip()
    if env in ("production", "prod"):
        if not mem_key or mem_key in KNOWN_INSECURE_SECRETS:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: "
                "MEMORY_ENCRYPTION_KEY must be explicitly set to a secure key in production. "
                f"Current value is {'empty' if not mem_key else 'a known insecure placeholder'}."
            )
        if mem_key == signing_secret:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: "
                "MEMORY_ENCRYPTION_KEY must be separate and distinct from SIGNING_SECRET in production."
            )
        return mem_key
    # Development / test default: fallback to separate derived key or provided key
    return mem_key or signing_secret or "adam-uk-gov-default-memory-encryption-key-2026"


def get_gateway_signing_secret() -> str:
    """Retrieve gateway HMAC signature secret with production separation checks."""
    env = os.getenv("ADAM_ENV", os.getenv("ENV", "development")).lower()
    gw_secret = os.getenv("GATEWAY_SIGNING_SECRET", "").strip()
    signing_secret = os.getenv("SIGNING_SECRET", "").strip()
    if env in ("production", "prod"):
        if not gw_secret or gw_secret in KNOWN_INSECURE_SECRETS:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: "
                "GATEWAY_SIGNING_SECRET must be explicitly set to a secure key in production. "
                f"Current value is {'empty' if not gw_secret else 'a known insecure placeholder'}."
            )
        if gw_secret == signing_secret:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: "
                "GATEWAY_SIGNING_SECRET must be separate and distinct from SIGNING_SECRET in production."
            )
        return gw_secret
    # Development / test default: fallback to separate dev key or provided key
    return gw_secret or "adam-uk-gov-default-gateway-signing-secret-2026"


# Cryptographic signing secret for inventory manifests and auth tokens
SIGNING_SECRET = get_signing_secret()
validate_production_database_url(DATABASE_URL)
MEMORY_ENCRYPTION_KEY = get_memory_encryption_key()
GATEWAY_SIGNING_SECRET = get_gateway_signing_secret()

# CORS allowed origins
DEFAULT_CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


def get_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "")
    if not raw.strip():
        return DEFAULT_CORS_ORIGINS
    return [o.strip() for o in raw.split(",") if o.strip()]


CORS_ORIGINS = get_cors_origins()
SECURITY_HEADERS_ENABLED = os.getenv("SECURITY_HEADERS_ENABLED", "true").lower() in ("true", "1", "yes")

# Maximum permitted file size for ingestion (e.g., 200MB)
MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024

# Default request timeout in seconds
REQUEST_TIMEOUT_SECONDS = 30.0

# Generation concurrency limit (R5)
MAX_CONCURRENT_GENERATIONS = int(os.getenv("MAX_CONCURRENT_GENERATIONS", "1"))

# Primary local model selection and runtime endpoints
PRIMARY_MODEL_ID = os.getenv("PRIMARY_MODEL_ID", "qwen3.5-4b-instruct-q4")
ADAM_MODEL_BACKEND = os.getenv("ADAM_MODEL_BACKEND", "ollama")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


# ── Hardware Memory Auto-Detection & Safe Context Window (Apple Silicon M2 / Low RAM) ──

def get_system_ram_bytes() -> Optional[int]:
    """Detect total system physical RAM in bytes across platforms."""
    # 1. psutil if installed
    try:
        import psutil
        return int(psutil.virtual_memory().total)
    except Exception:
        pass
    # 2. POSIX sysconf (macOS, Linux, BSD)
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        if pages > 0 and page_size > 0:
            return int(pages * page_size)
    except Exception:
        pass
    # 3. macOS / BSD sysctl
    try:
        import subprocess
        out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], stderr=subprocess.DEVNULL)
        val = int(out.strip())
        if val > 0:
            return val
    except Exception:
        pass
    # 4. Linux /proc/meminfo
    try:
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    kb = int(parts[1])
                    return kb * 1024
    except Exception:
        pass
    return None


def get_safe_context_window(requested_ctx: Optional[int] = None) -> int:
    """Calculate a hardware-aware safe context window cap in tokens for local LLM runtimes.

    Prevents Ollama Metal unified memory pre-allocation from causing swap thrashing
    or kernel out-of-memory crashes on memory-constrained devices (e.g. 8GB Apple Silicon).

    Hardware Tiers:
      - Total RAM <= 8GB (or unresolvable): default 4,096 tokens (hard max 8,192).
        A 4B Q4 model is ~2.65GB; a 4K KV cache is ~250MB, leaving ~5GB for macOS & apps.
      - Total RAM <= 16GB: default 8,192 tokens (hard max 16,384).
      - Total RAM <= 32GB: default 16,384 tokens (hard max 32,768).
      - Total RAM > 32GB: default 32,768 tokens (hard max 65,536).

    Overrides:
      `ADAM_CONTEXT_WINDOW` or `OLLAMA_NUM_CTX` environment variables take precedence.
    """
    env_override = os.getenv("ADAM_CONTEXT_WINDOW") or os.getenv("OLLAMA_NUM_CTX")
    if env_override:
        try:
            val = int(env_override.strip())
            if val > 0:
                return val
        except ValueError:
            pass

    ram_bytes = get_system_ram_bytes()
    if ram_bytes is not None:
        ram_gb = ram_bytes / (1024 ** 3)
    else:
        ram_gb = 8.0  # Conservative default when detection fails

    if ram_gb <= 9.0:  # <= ~8GB machines (e.g. 8GB MacBook Air M2)
        default_ctx = 4096
        max_ctx = 8192
    elif ram_gb <= 18.0:  # <= ~16GB machines
        default_ctx = 8192
        max_ctx = 16384
    elif ram_gb <= 34.0:  # <= ~32GB machines
        default_ctx = 16384
        max_ctx = 32768
    else:  # High-RAM workstations & servers
        default_ctx = 32768
        max_ctx = 65536

    if requested_ctx is None or requested_ctx <= 0:
        return default_ctx

    # If requested context is greater than the hardware safe maximum,
    # or is an unconstrained native ultra-long window (>= 32k tokens), clamp safely.
    if requested_ctx > max_ctx:
        if requested_ctx >= 32768:
            return default_ctx
        return max_ctx

    return requested_ctx


DEFAULT_SAFE_CONTEXT_WINDOW = get_safe_context_window()


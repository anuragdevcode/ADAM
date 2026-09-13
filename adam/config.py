"""Configuration settings for ADAM."""

import os
from pathlib import Path

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

# Database configuration
def get_database_url() -> str:
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

# Cryptographic signing secret for inventory manifests
SIGNING_SECRET = os.getenv("SIGNING_SECRET", "adam-uk-gov-default-auth-secret-key-2026")

# Maximum permitted file size for ingestion (e.g., 200MB)
MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024

# Default request timeout in seconds
REQUEST_TIMEOUT_SECONDS = 30.0

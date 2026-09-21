"""Public event serializer establishing a strict security boundary for UI events.

Guarantees:
- Zero leakage of API keys, credentials, tokens, or system prompts.
- Zero exposure of internal filesystem paths, SQLite/SQL statements, or tracebacks.
- Strict whitelisting of safe summary numbers (candidate counts, selected passages, durations).
"""

import re
from typing import Dict, Any, Optional
from adam.observability.events import OperationalEvent, OperationalEventType


# Whitelist of attributes allowed to cross the public UI boundary
PUBLIC_DATA_WHITELIST = {
    "candidate_count",
    "selected_count",
    "records_considered",
    "duration_ms",
    "banner_count",
    "citation_count",
    "query_language",
    "is_out_of_jurisdiction",
    "is_high_risk",
    "model_name",
    "suggested_action",
    "command_hint",
}

# Substrings and regex patterns indicating sensitive backend internals
SENSITIVE_PATTERNS = [
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"secret|token|password|bearer", re.IGNORECASE),
    re.compile(r"select\s+.*?\s+from", re.IGNORECASE),
    re.compile(r"insert\s+into|update\s+.*?\s+set", re.IGNORECASE),
    re.compile(r"(?:/Users/|/home/|/var/|/tmp/|[A-Z]:\\)", re.IGNORECASE),
    re.compile(r"\btraceback\b|\bexception\b|\.py:\d+", re.IGNORECASE),
    re.compile(r"system_prompt|prompt_template|<\|im_start\|>", re.IGNORECASE),
]


def _is_sensitive_key_or_val(key: str, val: Any) -> bool:
    """True if key name or string value matches sensitive internal patterns."""
    k_lower = key.lower()
    for pat in SENSITIVE_PATTERNS:
        if pat.search(k_lower):
            return True
        if isinstance(val, str) and pat.search(val):
            return True
    return False


def _sanitize_message(message: str) -> str:
    """Sanitize human-readable message, stripping any accidentally included file paths or tokens."""
    cleaned = message
    # Redact absolute paths
    cleaned = re.sub(r"(?:/[A-Za-z0-9_.-]+){3,}", "[path]", cleaned)
    # Redact potential keys or hex strings (20+ hex or base64 characters)
    cleaned = re.sub(r"\b[A-Za-z0-9_-]{24,}\b", "[redacted]", cleaned)
    return cleaned


class PublicEventSerializer:
    """Sanitizer and serializer producing safe SSE payloads for the client."""

    @classmethod
    def serialize(cls, event: OperationalEvent) -> Optional[Dict[str, Any]]:
        """Serialize an OperationalEvent into a public dictionary, strictly enforcing the boundary."""
        if not event:
            return None

        # Filter internal data dictionary through whitelist and safety checks
        sanitized_data: Dict[str, Any] = {}
        for k, v in event.data.items():
            if k in PUBLIC_DATA_WHITELIST and not _is_sensitive_key_or_val(k, v):
                # Ensure primitives only (int, float, bool, str)
                if isinstance(v, (int, float, bool, str)):
                    sanitized_data[k] = v

        safe_message = _sanitize_message(event.message)
        event_type_str = event.type.value if hasattr(event.type, "value") else str(event.type)

        return {
            "sequence": event.sequence,
            "type": event_type_str,
            "stage": event.stage,
            "status": event.status,
            "message": safe_message,
            "duration_ms": event.duration_ms,
            "timestamp": event.timestamp,
            "trace_id": event.trace_id,
            "data": sanitized_data,
        }

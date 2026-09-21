"""Local runtime discovery — detect installed model runtimes and enumerate their models.

This module is the entry point for the dynamic model discovery pipeline:

    LocalRuntimeProvider (detect) → list_models() → DiscoveredModel (DISCOVERED)
                                                              ↓
                                          validation.py → attestation.py → APPROVED

Design principles:
- Never instantiates a SingleModelLifecycleManager; discovery is read-only.
- Never sends user data or generation prompts during discovery.
- Normalises display names from arbitrary provider strings into HTML-safe text.
- Graceful degradation: an unavailable runtime returns an empty list, not an exception.
"""

from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from adam.model.runtime import OllamaModelRuntime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DiscoveredModel:
    """Lightweight descriptor for a model found during local runtime scanning.

    Status begins as ``DISCOVERED``.  It must pass deterministic validation and
    ADAM behavioural attestation before being promoted to ``APPROVED``.
    """
    model_id: str                       # provider-native identifier, e.g. "qwen3:4b"
    display_name: str                   # normalised, HTML-safe label
    provider: str                       # "ollama" | future runtime identifiers
    runtime: str                        # "ollama" | "lm_studio" | ...
    source: str = "discovered"          # always "discovered" at creation
    status: str = "DISCOVERED"          # DISCOVERED | APPROVED | LIMITED | UNAVAILABLE
    size_bytes: int = 0
    parameter_count: Optional[str] = None    # e.g. "3.1B"
    context_length: Optional[int] = None
    modified_at: Optional[str] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)
    discovered_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "display_name": self.display_name,
            "provider": self.provider,
            "runtime": self.runtime,
            "source": self.source,
            "status": self.status,
            "size_bytes": self.size_bytes,
            "size_mb": round(self.size_bytes / (1024 * 1024), 1) if self.size_bytes else 0,
            "parameter_count": self.parameter_count,
            "context_length": self.context_length,
            "modified_at": self.modified_at,
            "discovered_at": self.discovered_at,
        }


# ---------------------------------------------------------------------------
# Display-name normalisation
# ---------------------------------------------------------------------------

_SAFE_NAME_RE = re.compile(r"[^\w\s:.\-/()+]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s{2,}")
_MAX_DISPLAY_LEN = 80


def _sanitise_display_name(raw: str) -> str:
    """Return an HTML-safe, condensed display name from a provider-supplied string.

    Strips control characters, excess whitespace, and characters outside the
    allow-list.  Limits length to 80 characters.
    """
    if not raw:
        return "Unknown Model"
    # Strip control characters
    cleaned = "".join(ch for ch in raw if ch >= " ")
    # Remove unsafe characters
    cleaned = _SAFE_NAME_RE.sub("", cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    if not cleaned:
        return "Unknown Model"
    return cleaned[:_MAX_DISPLAY_LEN]


def _pretty_model_name(model_tag: str) -> str:
    """Convert an Ollama model tag like 'qwen2.5:3b' into a readable label."""
    tag = model_tag.strip()
    parts = tag.split(":")
    base = parts[0].replace("-", " ").replace("_", " ").strip().title()
    variant = parts[1].upper() if len(parts) > 1 else ""
    return f"{base} {variant}".strip() if variant else base


# ---------------------------------------------------------------------------
# Abstract provider interface
# ---------------------------------------------------------------------------

class LocalRuntimeProvider(ABC):
    """Abstract base for a local LLM runtime that can be interrogated for
    installed models without triggering generation.
    """

    @abstractmethod
    def detect(self) -> bool:
        """Return True if the runtime is running and reachable."""

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Return a dict with 'available', 'version', and 'host' keys."""

    @abstractmethod
    def list_models(self) -> List[DiscoveredModel]:
        """Return all locally installed models in the DISCOVERED state."""

    @abstractmethod
    def inspect_model(self, model_id: str) -> Dict[str, Any]:
        """Return low-level metadata dict for a single model without generating text."""


# ---------------------------------------------------------------------------
# Ollama implementation
# ---------------------------------------------------------------------------

class OllamaLocalProvider(LocalRuntimeProvider):
    """Wraps the existing OllamaModelRuntime infrastructure for discovery.

    Uses the same host/port convention (``OLLAMA_HOST`` env-var or
    ``http://localhost:11434``).  All HTTP calls are read-only (GET only)
    during discovery; no generation is triggered.
    """

    DISCOVERY_TIMEOUT = 3.0   # seconds — fast check, not a generation call
    TAG_ENDPOINT = "/api/tags"
    SHOW_ENDPOINT = "/api/show"

    def __init__(self, host: Optional[str] = None):
        self.host = (host or OllamaModelRuntime.DEFAULT_HOST).rstrip("/")
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                base_url=self.host,
                timeout=self.DISCOVERY_TIMEOUT,
            )
        return self._client

    # ------------------------------------------------------------------
    # LocalRuntimeProvider interface
    # ------------------------------------------------------------------

    def detect(self) -> bool:
        """Ping /api/tags to confirm Ollama is running."""
        try:
            r = self._get_client().get(self.TAG_ENDPOINT)
            return r.status_code == 200
        except Exception:
            return False

    def health_check(self) -> Dict[str, Any]:
        """Return structured health data for the Ollama service."""
        try:
            r = self._get_client().get(self.TAG_ENDPOINT)
            if r.status_code == 200:
                data = r.json()
                return {
                    "available": True,
                    "host": self.host,
                    "model_count": len(data.get("models", [])),
                    "runtime": "ollama",
                }
            return {"available": False, "host": self.host, "runtime": "ollama",
                    "error": f"HTTP {r.status_code}"}
        except Exception as exc:
            return {"available": False, "host": self.host, "runtime": "ollama",
                    "error": str(exc)}

    def list_models(self) -> List[DiscoveredModel]:
        """List all models installed in the local Ollama daemon."""
        try:
            r = self._get_client().get(self.TAG_ENDPOINT)
            if r.status_code != 200:
                logger.debug("Ollama /api/tags returned HTTP %s — no models discovered.", r.status_code)
                return []
            data = r.json()
        except Exception as exc:
            logger.debug("Ollama discovery failed (server may be offline): %s", exc)
            return []

        results: List[DiscoveredModel] = []
        for entry in data.get("models", []):
            try:
                raw_name: str = entry.get("name", "")
                if not raw_name:
                    continue
                size_bytes = int(entry.get("size", 0) or 0)
                modified_at = entry.get("modified_at")
                details = entry.get("details", {}) or {}
                param_str = details.get("parameter_size") or None
                context_len = details.get("context_length") or None
                if context_len is not None:
                    try:
                        context_len = int(context_len)
                    except (TypeError, ValueError):
                        context_len = None

                results.append(DiscoveredModel(
                    model_id=raw_name,
                    display_name=_sanitise_display_name(_pretty_model_name(raw_name)),
                    provider="ollama",
                    runtime="ollama",
                    source="discovered",
                    status="DISCOVERED",
                    size_bytes=size_bytes,
                    parameter_count=param_str,
                    context_length=context_len,
                    modified_at=modified_at,
                    raw_metadata=entry,
                    discovered_at=time.time(),
                ))
            except Exception as exc:
                logger.warning("Could not parse Ollama model entry %r: %s", entry, exc)
                continue

        logger.info("Ollama discovery found %d installed model(s).", len(results))
        return results

    def inspect_model(self, model_id: str) -> Dict[str, Any]:
        """Return raw /api/show metadata for a single model."""
        try:
            r = self._get_client().post(
                self.SHOW_ENDPOINT,
                json={"name": model_id},
            )
            if r.status_code == 200:
                return r.json()
            return {"error": f"HTTP {r.status_code}"}
        except Exception as exc:
            return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Multi-provider orchestration
# ---------------------------------------------------------------------------

# Registry of all supported local providers (extend here for LM Studio, vLLM etc.)
_LOCAL_PROVIDERS: List[type] = [OllamaLocalProvider]


def run_local_discovery() -> List[DiscoveredModel]:
    """Scan all registered local runtime providers and return discovered models.

    Each provider is tried independently; a failure in one provider does not
    prevent others from running.

    Returns a deduplicated list (by model_id within the same provider).
    """
    all_models: List[DiscoveredModel] = []
    seen: set = set()

    for provider_cls in _LOCAL_PROVIDERS:
        try:
            provider = provider_cls()
            if not provider.detect():
                logger.debug("%s not available — skipping.", provider_cls.__name__)
                continue
            models = provider.list_models()
            for m in models:
                key = (m.provider, m.model_id)
                if key not in seen:
                    seen.add(key)
                    all_models.append(m)
        except Exception as exc:
            logger.warning(
                "Unexpected error in local runtime provider %s: %s",
                provider_cls.__name__,
                exc,
            )

    return all_models

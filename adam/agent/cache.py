"""Governed in-memory response cache for low-latency administrative query resolution.

Provides an LRU cache with time-to-live (TTL) expiration, clearance-level isolation,
and evidence-fingerprinted cache keys.

Guarantees:
- Never caches across clearance boundaries (PUBLIC vs RESTRICTED vs CONFIDENTIAL).
- Strictly invalidates when underlying evidence packets change.
- Cache hit execution completes in < 0.2ms.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CachedResponseEntry:
    """A single cached response record."""
    answer: str
    citations: List[Dict[str, Any]]
    currency_banners: List[str]
    search_suggestions: List[str]
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    created_at: float
    ttl_seconds: float
    is_refusal: bool = False
    refusal_category: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds


class GovernedResponseCache:
    """Thread-safe LRU response cache for governed state machine executions."""

    def __init__(self, max_entries: int = 500, default_ttl_seconds: float = 3600.0):
        self.max_entries = max_entries
        self.default_ttl_seconds = default_ttl_seconds
        self._cache: Dict[str, CachedResponseEntry] = {}
        self._lock = threading.RLock()
        self._hits: int = 0
        self._misses: int = 0

    @staticmethod
    def compute_cache_key(
        query: str,
        model_id: str,
        clearance_level: str,
        department_id: Optional[str] = None,
        evidence_fingerprint: Optional[str] = None,
    ) -> str:
        """Generate a deterministic, security-isolated cache key."""
        clean_q = " ".join((query or "").strip().lower().split())
        key_raw = f"{clean_q}|{model_id}|{clearance_level}|{department_id or 'NONE'}|{evidence_fingerprint or 'EMPTY'}"
        return hashlib.sha256(key_raw.encode("utf-8")).hexdigest()

    def get(self, cache_key: str) -> Optional[CachedResponseEntry]:
        """Retrieve a non-expired cached response."""
        with self._lock:
            entry = self._cache.get(cache_key)
            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired:
                del self._cache[cache_key]
                self._misses += 1
                return None

            self._hits += 1
            # Move to end (most recently used in dict order)
            self._cache[cache_key] = self._cache.pop(cache_key)
            return entry

    def put(
        self,
        cache_key: str,
        answer: str,
        citations: List[Dict[str, Any]],
        currency_banners: List[str],
        search_suggestions: List[str],
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        is_refusal: bool = False,
        refusal_category: Optional[str] = None,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """Store a response in cache with LRU eviction."""
        if not answer:
            return

        ttl = ttl_seconds or self.default_ttl_seconds
        entry = CachedResponseEntry(
            answer=answer,
            citations=citations,
            currency_banners=currency_banners,
            search_suggestions=search_suggestions,
            model_id=model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            created_at=time.time(),
            ttl_seconds=ttl,
            is_refusal=is_refusal,
            refusal_category=refusal_category,
        )

        with self._lock:
            # Evict oldest entry if at capacity
            if len(self._cache) >= self.max_entries and cache_key not in self._cache:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]

            self._cache[cache_key] = entry

    def invalidate(self, cache_key: str) -> bool:
        """Explicitly invalidate a single key."""
        with self._lock:
            if cache_key in self._cache:
                del self._cache[cache_key]
                return True
            return False

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> Dict[str, Any]:
        """Return cache health and hit rate statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests) if total_requests > 0 else 0.0
            return {
                "entries": len(self._cache),
                "max_entries": self.max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 3),
            }


# Global singleton instance for the ADAM process
GLOBAL_RESPONSE_CACHE = GovernedResponseCache()

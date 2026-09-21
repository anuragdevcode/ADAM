"""Tests for GovernedResponseCache and state machine caching integration."""
import time
import pytest
from adam.agent.cache import GovernedResponseCache, CachedResponseEntry, GLOBAL_RESPONSE_CACHE


def test_cache_hit_and_put():
    cache = GovernedResponseCache(max_entries=10, default_ttl_seconds=60.0)
    key = cache.compute_cache_key(
        query="What is the procurement limit?",
        model_id="qwen2.5:3b",
        clearance_level="PUBLIC",
        department_id="FINANCE_TREASURY",
    )

    assert cache.get(key) is None
    assert cache.stats()["misses"] == 1

    cache.put(
        cache_key=key,
        answer="The procurement limit is Rs. 25 Lakhs.",
        citations=[{"document_title": "Procurement Rules 2023", "department": "Finance"}],
        currency_banners=[],
        search_suggestions=[],
        model_id="qwen2.5:3b",
        prompt_tokens=15,
        completion_tokens=20,
    )

    entry = cache.get(key)
    assert entry is not None
    assert entry.answer == "The procurement limit is Rs. 25 Lakhs."
    assert len(entry.citations) == 1
    assert entry.citations[0]["document_title"] == "Procurement Rules 2023"
    assert cache.stats()["hits"] == 1


def test_cache_hit_latency_sub_millisecond():
    cache = GovernedResponseCache()
    key = cache.compute_cache_key(
        query="Benchmark test query",
        model_id="qwen2.5:3b",
        clearance_level="PUBLIC",
    )
    cache.put(
        cache_key=key,
        answer="Fast response.",
        citations=[],
        currency_banners=[],
        search_suggestions=[],
        model_id="qwen2.5:3b",
        prompt_tokens=5,
        completion_tokens=5,
    )

    t0 = time.perf_counter()
    entry = cache.get(key)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert entry is not None
    assert elapsed_ms < 0.5, f"Cache retrieval took {elapsed_ms:.3f}ms (expected < 0.5ms)"


def test_clearance_isolation():
    """Security guarantee: PUBLIC query cache key must NOT match RESTRICTED or CONFIDENTIAL."""
    k_pub = GovernedResponseCache.compute_cache_key(
        query="Cabinet confidential agenda",
        model_id="qwen2.5:3b",
        clearance_level="PUBLIC",
    )
    k_res = GovernedResponseCache.compute_cache_key(
        query="Cabinet confidential agenda",
        model_id="qwen2.5:3b",
        clearance_level="RESTRICTED",
    )
    k_conf = GovernedResponseCache.compute_cache_key(
        query="Cabinet confidential agenda",
        model_id="qwen2.5:3b",
        clearance_level="CONFIDENTIAL",
    )

    assert k_pub != k_res
    assert k_pub != k_conf
    assert k_res != k_conf


def test_department_isolation():
    k_fin = GovernedResponseCache.compute_cache_key(
        query="travel allowance",
        model_id="qwen2.5:3b",
        clearance_level="PUBLIC",
        department_id="FINANCE",
    )
    k_pwd = GovernedResponseCache.compute_cache_key(
        query="travel allowance",
        model_id="qwen2.5:3b",
        clearance_level="PUBLIC",
        department_id="PWD",
    )
    assert k_fin != k_pwd


def test_evidence_fingerprint_invalidation():
    k1 = GovernedResponseCache.compute_cache_key(
        query="pension rules",
        model_id="qwen2.5:3b",
        clearance_level="PUBLIC",
        evidence_fingerprint="fp_hash_123",
    )
    k2 = GovernedResponseCache.compute_cache_key(
        query="pension rules",
        model_id="qwen2.5:3b",
        clearance_level="PUBLIC",
        evidence_fingerprint="fp_hash_456",
    )
    assert k1 != k2


def test_ttl_expiration():
    cache = GovernedResponseCache(default_ttl_seconds=0.05)
    key = "expiring_key"
    cache.put(
        cache_key=key,
        answer="Short-lived answer",
        citations=[],
        currency_banners=[],
        search_suggestions=[],
        model_id="qwen2.5:3b",
        prompt_tokens=1,
        completion_tokens=1,
        ttl_seconds=0.05,
    )

    assert cache.get(key) is not None
    time.sleep(0.06)
    assert cache.get(key) is None
    assert cache.stats()["misses"] >= 1


def test_lru_eviction():
    cache = GovernedResponseCache(max_entries=2)
    cache.put("k1", "a1", [], [], [], "m", 1, 1)
    cache.put("k2", "a2", [], [], [], "m", 1, 1)

    # Access k1 to make k2 the least recently used
    _ = cache.get("k1")

    # Insert k3, should evict k2
    cache.put("k3", "a3", [], [], [], "m", 1, 1)

    assert cache.get("k1") is not None
    assert cache.get("k2") is None
    assert cache.get("k3") is not None

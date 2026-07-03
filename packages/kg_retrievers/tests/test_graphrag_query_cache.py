"""Tests for the GraphRAG global-search query cache (§11.7)."""

from __future__ import annotations

import json

from kg_retrievers.graphrag_query_cache import (
    CacheEntry,
    GlobalSearchCache,
    make_cache_key,
)


def test_make_cache_key_stable_and_level_sensitive() -> None:
    """Same inputs -> same key; changing the level -> different key."""
    a = make_cache_key("What is X?", "build-1", 2)
    b = make_cache_key("What is X?", "build-1", 2)
    c = make_cache_key("What is X?", "build-1", 3)
    assert a == b
    assert a != c
    assert len(a) == 64  # sha256 hex


def test_make_cache_key_case_and_whitespace_insensitive() -> None:
    """Case-/whitespace-different queries with same content produce identical keys."""
    k1 = make_cache_key("Hello World", "v1", 1)
    k2 = make_cache_key("  hello world  ", "v1", 1)
    assert k1 == k2
    # A genuinely different build_version must still fork the key.
    assert make_cache_key("hello world", "v2", 1) != k1


def test_put_then_get_within_ttl_returns_value() -> None:
    """put then get before expiry returns the stored value."""
    cache = GlobalSearchCache(ttl_seconds=100.0)
    key = make_cache_key("q", "v1", 0)
    value = {"answer": "42", "sources": [1, 2, 3]}
    cache.put(key, value, now=1000.0)
    assert cache.get(key, now=1050.0) == value


def test_get_after_expiry_returns_none() -> None:
    """get with now >= expires_at returns None (exact boundary is expired)."""
    cache = GlobalSearchCache(ttl_seconds=10.0)
    key = make_cache_key("q", "v1", 0)
    cache.put(key, {"answer": "x"}, now=100.0)
    assert cache.get(key, now=110.0) is None  # now == expires_at -> expired
    assert cache.get(key, now=115.0) is None
    assert cache.get("missing-key", now=100.0) is None


def test_evict_expired_removes_only_expired_and_returns_count() -> None:
    """evict_expired drops expired entries only and returns their count."""
    cache = GlobalSearchCache(ttl_seconds=10.0)
    cache.put("a", {"v": 1}, now=0.0)  # expires_at = 10
    cache.put("b", {"v": 2}, now=5.0)  # expires_at = 15
    cache.put("c", {"v": 3}, now=8.0)  # expires_at = 18
    removed = cache.evict_expired(now=16.0)  # a, b expired; c live
    assert removed == 2
    assert cache.size() == 1
    assert cache.get("c", now=16.0) == {"v": 3}
    assert cache.get("a", now=16.0) is None


def test_size_reflects_live_entries() -> None:
    """size counts stored entries, and drops after eviction."""
    cache = GlobalSearchCache(ttl_seconds=50.0)
    assert cache.size() == 0
    cache.put("a", {"v": 1}, now=0.0)
    cache.put("b", {"v": 2}, now=0.0)
    assert cache.size() == 2
    cache.evict_expired(now=100.0)
    assert cache.size() == 0


def test_cache_entry_as_dict_serializable_and_expiry_math() -> None:
    """as_dict round-trips through json and expires_at == created_at + ttl_seconds."""
    cache = GlobalSearchCache(ttl_seconds=30.0)
    entry = cache.put("k", {"answer": "ok"}, now=100.0)
    assert isinstance(entry, CacheEntry)
    assert entry.expires_at == entry.created_at + 30.0
    assert entry.created_at == 100.0
    assert entry.expires_at == 130.0
    payload = entry.as_dict()
    assert json.loads(json.dumps(payload)) == payload
    assert payload["key"] == "k"
    assert payload["value"] == {"answer": "ok"}

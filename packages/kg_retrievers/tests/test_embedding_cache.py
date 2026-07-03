"""Hand-checked tests for the §4.7 content-hashed LRU embedding cache.

Каждое ожидаемое значение посчитано вручную: content-ключи сверяются с эталонным
sha256 (``sha256("abc")`` = ``ba7816bf…``); LRU-вытеснение и счётчики hits/misses
прослежены пошагово по формулировкам :mod:`kg_retrievers.embedding_cache`.
"""

from __future__ import annotations

import hashlib

import pytest

from kg_retrievers.embedding_cache import (
    DEFAULT_MAXSIZE,
    CacheStats,
    EmbeddingCache,
    content_key,
)

# ---------------------------------------------------------------------------
# content_key — deterministic sha256 over the text (same text → same key)
# ---------------------------------------------------------------------------


def test_content_key_matches_reference_sha256() -> None:
    """content_key("abc") == sha256("abc") hex → known ba7816bf… digest."""
    expected = hashlib.sha256(b"abc").hexdigest()
    assert content_key("abc") == expected
    assert content_key("abc").startswith("ba7816bf")


def test_content_key_same_text_same_key() -> None:
    """Identical text always hashes to the identical cache key (position-independent)."""
    assert content_key("обратный осмос") == content_key("обратный осмос")


def test_content_key_differs_for_different_text() -> None:
    """A one-character change yields a different key (no collisions here)."""
    assert content_key("abc") != content_key("abd")


# ---------------------------------------------------------------------------
# put / get — round-trip, miss, copy isolation
# ---------------------------------------------------------------------------


def test_put_get_round_trip() -> None:
    """A stored vector comes back value-equal on lookup by the same text."""
    cache = EmbeddingCache(maxsize=4)
    cache.put("query", [0.1, 0.2, 0.3])
    assert cache.get("query") == [0.1, 0.2, 0.3]


def test_miss_returns_none() -> None:
    """Looking up a never-stored text returns None (not KeyError, not [])."""
    cache = EmbeddingCache(maxsize=4)
    assert cache.get("absent") is None


def test_returned_vector_is_a_copy() -> None:
    """Mutating the returned list must not corrupt the cached vector."""
    cache = EmbeddingCache(maxsize=2)
    cache.put("t", [1.0, 2.0])
    got = cache.get("t")
    assert got is not None
    got.append(99.0)
    assert cache.get("t") == [1.0, 2.0]  # cache untouched by caller mutation


def test_put_same_text_updates_not_duplicates() -> None:
    """Re-putting the same text overwrites its vector and keeps size at 1."""
    cache = EmbeddingCache(maxsize=4)
    cache.put("k", [1.0])
    cache.put("k", [2.0, 3.0])
    assert len(cache) == 1
    assert cache.get("k") == [2.0, 3.0]


# ---------------------------------------------------------------------------
# get_or_compute — lazy compute exactly once, then serve from cache
# ---------------------------------------------------------------------------


def test_get_or_compute_computes_and_caches() -> None:
    """First call computes via fn and stores; the value is retrievable afterwards."""
    cache = EmbeddingCache(maxsize=4)
    calls: list[str] = []

    def fn(text: str) -> list[float]:
        calls.append(text)
        return [float(len(text))]

    out = cache.get_or_compute("hello", fn)
    assert out == [5.0]
    assert calls == ["hello"]
    assert cache.get("hello") == [5.0]


def test_get_or_compute_serves_cache_on_second_call() -> None:
    """A cached text is served without invoking fn a second time (fn called once)."""
    cache = EmbeddingCache(maxsize=4)
    calls: list[str] = []

    def fn(text: str) -> list[float]:
        calls.append(text)
        return [1.0, 1.0]

    first = cache.get_or_compute("x", fn)
    second = cache.get_or_compute("x", fn)
    assert first == [1.0, 1.0]
    assert second == [1.0, 1.0]
    assert calls == ["x"]  # fn ran exactly once


# ---------------------------------------------------------------------------
# LRU eviction — bounded size, least-recently-used victim, recency refresh
# ---------------------------------------------------------------------------


def test_lru_eviction_at_maxsize() -> None:
    """Inserting past maxsize evicts the least-recently-used (oldest) entry."""
    cache = EmbeddingCache(maxsize=2)
    cache.put("a", [1.0])
    cache.put("b", [2.0])
    cache.put("c", [3.0])  # 'a' is LRU → evicted
    assert cache.get("a") is None
    assert cache.get("b") == [2.0]
    assert cache.get("c") == [3.0]
    assert len(cache) == 2


def test_lru_access_refreshes_recency() -> None:
    """A get() on the oldest key makes it MRU, so the *next* insert evicts the other."""
    cache = EmbeddingCache(maxsize=2)
    cache.put("a", [1.0])
    cache.put("b", [2.0])
    assert cache.get("a") == [1.0]  # 'a' now most-recently-used, 'b' becomes LRU
    cache.put("c", [3.0])  # evicts 'b', not 'a'
    assert cache.get("b") is None
    assert cache.get("a") == [1.0]
    assert cache.get("c") == [3.0]


def test_size_bounded_by_maxsize() -> None:
    """Flooding with 50 distinct texts into a size-10 cache never exceeds 10 entries."""
    cache = EmbeddingCache(maxsize=10)
    for i in range(50):
        cache.put(f"t{i}", [float(i)])
    assert len(cache) == 10
    assert cache.stats()["size"] == 10
    # Only the last 10 inserted (t40..t49) survive; earlier ones were evicted.
    assert cache.get("t49") == [49.0]
    assert cache.get("t39") is None


# ---------------------------------------------------------------------------
# stats — hit/miss accounting and CacheStats snapshot
# ---------------------------------------------------------------------------


def test_stats_counts_hits_and_misses() -> None:
    """Each get is tallied: hit on present key, miss on absent key; size is live count."""
    cache = EmbeddingCache(maxsize=4)
    assert cache.stats() == {"hits": 0, "misses": 0, "size": 0}
    cache.put("a", [1.0])
    assert cache.get("a") == [1.0]  # hit
    assert cache.get("a") == [1.0]  # hit
    assert cache.get("missing") is None  # miss
    assert cache.stats() == {"hits": 2, "misses": 1, "size": 1}


def test_get_or_compute_counts_one_miss_then_one_hit() -> None:
    """First get_or_compute is a miss; the second is a hit — reflected in stats."""
    cache = EmbeddingCache(maxsize=4)
    cache.get_or_compute("q", lambda _t: [0.0])  # miss
    cache.get_or_compute("q", lambda _t: [0.0])  # hit
    assert cache.stats() == {"hits": 1, "misses": 1, "size": 1}


def test_snapshot_is_frozen_with_as_dict() -> None:
    """snapshot() returns an immutable CacheStats whose as_dict matches stats()."""
    cache = EmbeddingCache(maxsize=4)
    cache.put("a", [1.0])
    cache.get("a")  # 1 hit
    cache.get("z")  # 1 miss
    snap = cache.snapshot()
    assert isinstance(snap, CacheStats)
    assert snap.as_dict() == {"hits": 1, "misses": 1, "size": 1}
    assert snap.lookups == 2
    assert snap.hit_rate == 0.5
    with pytest.raises(AttributeError):
        snap.hits = 99  # type: ignore[misc]  # frozen dataclass is read-only


# ---------------------------------------------------------------------------
# clear / construction guards
# ---------------------------------------------------------------------------


def test_clear_empties_and_resets_stats() -> None:
    """clear() drops all entries and zeroes hit/miss counters back to fresh."""
    cache = EmbeddingCache(maxsize=4)
    cache.put("a", [1.0])
    cache.get("a")
    cache.get("nope")
    cache.clear()
    assert len(cache) == 0
    assert cache.get("a") is None  # this miss lands after the reset
    assert cache.stats() == {"hits": 0, "misses": 1, "size": 0}


def test_contains_does_not_count_as_lookup() -> None:
    """__contains__ checks membership without touching hit/miss counters."""
    cache = EmbeddingCache(maxsize=4)
    cache.put("a", [1.0])
    assert "a" in cache
    assert "b" not in cache
    assert cache.stats() == {"hits": 0, "misses": 0, "size": 1}


def test_default_maxsize_is_1024() -> None:
    """The documented default cap is 1024 entries (§4.7)."""
    cache = EmbeddingCache()
    assert cache.maxsize == DEFAULT_MAXSIZE == 1024


def test_invalid_maxsize_rejected() -> None:
    """maxsize below 1 is a construction error (an unbounded cache would defeat LRU)."""
    with pytest.raises(ValueError, match="maxsize must be >= 1"):
        EmbeddingCache(maxsize=0)

"""Hand-checked tests for the §11.7 GraphRAG global-search TTL cache.

Каждое ожидаемое значение посчитано вручную: query-хэши сверяются с эталонным
sha256 нормализованной формы (``sha256("overview")[:16]``); истечение TTL
прослежено пошагово через инъектированные фейковые часы (список отсчётов).
"""

from __future__ import annotations

import hashlib

import pytest

from kg_retrievers.graphrag_search_cache import (
    QUERY_HASH_LEN,
    CacheKey,
    GlobalSearchCache,
    make_key,
    normalize_query,
)


class FakeClock:
    """Deterministic clock: returns preset ticks in order, holding the last one."""

    def __init__(self, ticks: list[float]) -> None:
        self._ticks = list(ticks)
        self._i = 0

    def __call__(self) -> float:
        tick = self._ticks[min(self._i, len(self._ticks) - 1)]
        self._i += 1
        return tick


# ---------------------------------------------------------------------------
# normalize_query + make_key — sha256[:16] over the normalized query
# ---------------------------------------------------------------------------


def test_normalize_query_strips_and_lowercases() -> None:
    """normalize_query("Overview ") == "overview" (strip then lowercase)."""
    assert normalize_query("Overview ") == "overview"
    assert normalize_query("  OVERVIEW  ") == "overview"


def test_make_key_query_hash_matches_reference_sha256() -> None:
    """query_hash == sha256("overview") hex truncated to 16 chars."""
    expected = hashlib.sha256(b"overview").hexdigest()[:QUERY_HASH_LEN]
    key = make_key("Overview ", "v1", 2)
    assert key.query_hash == expected
    assert len(key.query_hash) == 16


def test_make_key_normalization_collapses_case_and_space() -> None:
    """make_key('Overview ','v1',2) == make_key('overview','v1',2) (normalization)."""
    assert make_key("Overview ", "v1", 2) == make_key("overview", "v1", 2)


def test_make_key_differs_for_different_level() -> None:
    """Same normalized query but level 1 vs 2 → different keys."""
    assert make_key("overview", "v1", 2) != make_key("overview", "v1", 1)


def test_make_key_build_versions_never_collide() -> None:
    """Two different build_versions of the same query/level never share a key."""
    assert make_key("overview", "v1", 2) != make_key("overview", "v2", 2)


# ---------------------------------------------------------------------------
# CacheKey — as_dict / to_str shapes
# ---------------------------------------------------------------------------


def test_cachekey_as_dict_level_is_int() -> None:
    """CacheKey.as_dict()['level'] is an int (type preserved through projection)."""
    d = make_key("overview", "v1", 2).as_dict()
    assert d == {"query_hash": d["query_hash"], "build_version": "v1", "level": 2}
    assert isinstance(d["level"], int)


def test_cachekey_to_str_joins_fields() -> None:
    """to_str joins the three fields with ':' → 'abcd:v1:2'."""
    key = CacheKey(query_hash="abcd", build_version="v1", level=2)
    assert key.to_str() == "abcd:v1:2"


# ---------------------------------------------------------------------------
# GlobalSearchCache — put/get, hits/misses, TTL expiry, stats, eviction
# ---------------------------------------------------------------------------


def test_put_then_get_returns_value_and_counts_hit() -> None:
    """put then get returns the stored value and increments hits."""
    cache = GlobalSearchCache(ttl_seconds=100, clock=FakeClock([0.0]))
    key = make_key("overview", "v1", 2)
    cache.put(key, {"answer": 42})
    assert cache.get(key) == {"answer": 42}
    assert cache.stats()["hits"] == 1
    assert cache.stats()["misses"] == 0


def test_get_missing_key_returns_none_and_counts_miss() -> None:
    """get on a missing key returns None and increments misses."""
    cache = GlobalSearchCache(ttl_seconds=100, clock=FakeClock([0.0]))
    assert cache.get(make_key("nope", "v1", 2)) is None
    assert cache.stats()["misses"] == 1
    assert cache.stats()["hits"] == 0


def test_ttl_expiry_get_returns_none_and_evict_removes_entry() -> None:
    """Clock advanced past ttl: get returns None and evict_expired removed the entry."""
    # ticks: put@0, get@10 (11s TTL → still live), get@20 (expired), evict@20.
    clock = FakeClock([0.0, 10.0, 20.0, 20.0])
    cache = GlobalSearchCache(ttl_seconds=11, clock=clock)
    key = make_key("overview", "v1", 2)
    cache.put(key, "cached")
    assert cache.get(key) == "cached"  # 10 - 0 = 10 <= 11 → live hit
    assert cache.get(key) is None  # 20 - 0 = 20 > 11 → expired miss, slot dropped
    assert len(cache) == 0  # lazy get already removed the stale slot
    assert cache.evict_expired() == 0  # nothing left to sweep


def test_evict_expired_returns_count_of_removed() -> None:
    """evict_expired removes stale entries and returns their number."""
    clock = FakeClock([0.0, 0.0, 100.0, 100.0])  # put a@0, put b@0, evict@100
    cache = GlobalSearchCache(ttl_seconds=10, clock=clock)
    cache.put(make_key("a", "v1", 1), 1)
    cache.put(make_key("b", "v1", 1), 2)
    assert cache.evict_expired() == 2  # both older than 10s at t=100
    assert len(cache) == 0


def test_stats_size_reflects_live_entries() -> None:
    """stats()['size'] reflects live entries; expired ones are excluded."""
    # clock() fires once per put and once per stats: put a@0, put b@0, stats@5, stats@50.
    clock = FakeClock([0.0, 0.0, 5.0, 50.0])
    cache = GlobalSearchCache(ttl_seconds=10, clock=clock)
    cache.put(make_key("a", "v1", 1), 1)
    cache.put(make_key("b", "v1", 1), 2)
    assert cache.stats()["size"] == 2  # both within TTL at t=5
    assert cache.stats()["size"] == 0  # both expired at t=50


def test_put_same_key_refreshes_timestamp() -> None:
    """A repeated put replaces the value and restarts the TTL clock."""
    # put@0, put@8 (refresh), get@10 (10-8=2 <= 5 → live).
    clock = FakeClock([0.0, 8.0, 10.0])
    cache = GlobalSearchCache(ttl_seconds=5, clock=clock)
    key = make_key("overview", "v1", 2)
    cache.put(key, "old")
    cache.put(key, "new")
    assert cache.get(key) == "new"


def test_different_build_versions_do_not_collide_in_cache() -> None:
    """Two build_versions coexist as distinct slots with independent values."""
    cache = GlobalSearchCache(ttl_seconds=100, clock=FakeClock([0.0]))
    cache.put(make_key("overview", "v1", 2), "answer-v1")
    cache.put(make_key("overview", "v2", 2), "answer-v2")
    assert cache.get(make_key("overview", "v1", 2)) == "answer-v1"
    assert cache.get(make_key("overview", "v2", 2)) == "answer-v2"
    assert cache.stats()["size"] == 2


def test_negative_ttl_rejected() -> None:
    """A negative ttl_seconds is rejected at construction."""
    with pytest.raises(ValueError, match="ttl_seconds"):
        GlobalSearchCache(ttl_seconds=-1)

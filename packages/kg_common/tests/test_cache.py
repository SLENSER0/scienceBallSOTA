"""TTL + LRU retrieval-cache tests (§12.11 retrieval caching, embedded Redis-equivalent).

Every test drives an injected :class:`FakeClock`; TTL expiry is exercised by
advancing the fake counter, never by real ``time.sleep``. Counts are chosen to
be hand-checkable.
"""

from __future__ import annotations

import pytest

from kg_common.cache import CacheStats, TtlLruCache, cached


class FakeClock:
    """Deterministic, manually-advanced monotonic clock (§12.11 «детерминизм»)."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, dt: float) -> None:
        self.now += dt


def test_get_miss_then_set_then_hit() -> None:
    cache: TtlLruCache[str] = TtlLruCache(maxsize=4, ttl_seconds=100, clock=FakeClock())
    assert cache.get("k") is None  # absent -> miss, returns default
    cache.set("k", "v")
    assert cache.get("k") == "v"  # now present -> hit
    st = cache.stats()
    assert st["hits"] == 1
    assert st["misses"] == 1
    assert st["size"] == 1


def test_ttl_expiry_via_advancing_clock() -> None:
    clock = FakeClock()
    cache: TtlLruCache[str] = TtlLruCache(maxsize=4, ttl_seconds=300, clock=clock)
    cache.set("k", "v")
    assert cache.get("k") == "v"  # alive at t=0
    clock.advance(300)  # reach the exact expiry boundary
    assert cache.get("k") is None  # now >= expiry -> expired, miss
    # A TTL expiry is a miss, never an eviction.
    assert cache.stats()["evictions"] == 0


def test_clock_injection_controls_expiry_exactly() -> None:
    clock = FakeClock()
    cache: TtlLruCache[str] = TtlLruCache(maxsize=4, ttl_seconds=10, clock=clock)
    cache.set("k", "v")  # stored at t=0, expiry == 10
    clock.advance(9)
    assert cache.get("k") == "v"  # t=9 < 10 -> still alive (get does not refresh TTL)
    clock.advance(1)  # t == 10, the exact boundary
    assert cache.get("k") is None  # now >= expiry -> expired to the second


def test_lru_eviction_at_maxsize() -> None:
    cache: TtlLruCache[int] = TtlLruCache(maxsize=2, ttl_seconds=1000, clock=FakeClock())
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1  # touch "a" -> "b" becomes least-recently-used
    cache.set("c", 3)  # over capacity -> evict LRU == "b"
    assert cache.get("b") is None  # evicted
    assert cache.get("a") == 1  # survived (was most-recently-used)
    assert cache.get("c") == 3  # newest
    assert cache.stats()["evictions"] == 1
    assert cache.stats()["size"] == 2


def test_get_or_compute_computes_once_then_caches() -> None:
    calls: list[int] = []

    def compute() -> int:
        calls.append(1)
        return 99

    cache: TtlLruCache[int] = TtlLruCache(maxsize=4, ttl_seconds=100, clock=FakeClock())
    assert cache.get_or_compute("k", compute) == 99  # miss -> computes
    assert cache.get_or_compute("k", compute) == 99  # hit -> cached, no compute
    assert calls == [1]  # computed exactly once
    st = cache.stats()
    assert st["hits"] == 1
    assert st["misses"] == 1


def test_get_or_compute_recomputes_after_ttl_expiry() -> None:
    calls: list[int] = []
    clock = FakeClock()

    def compute() -> int:
        calls.append(1)
        return len(calls)

    cache: TtlLruCache[int] = TtlLruCache(maxsize=4, ttl_seconds=50, clock=clock)
    assert cache.get_or_compute("k", compute) == 1  # first compute
    clock.advance(50)  # expire the entry
    assert cache.get_or_compute("k", compute) == 2  # recomputed after expiry
    assert calls == [1, 1]


def test_invalidate_removes_entry() -> None:
    cache: TtlLruCache[int] = TtlLruCache(maxsize=4, ttl_seconds=100, clock=FakeClock())
    cache.set("k", 5)
    assert cache.get("k") == 5
    assert cache.invalidate("k") is True  # removed
    assert cache.get("k") is None  # gone
    assert cache.invalidate("k") is False  # nothing left to remove
    assert cache.invalidate("never-existed") is False


def test_clear_resets_entries_and_counters() -> None:
    cache: TtlLruCache[int] = TtlLruCache(maxsize=4, ttl_seconds=100, clock=FakeClock())
    cache.set("a", 1)
    cache.get("a")  # hit
    cache.get("z")  # miss
    cache.clear()
    assert cache.get("a") is None  # entries gone
    # Right after clear (before the miss above is re-counted) counters are zero;
    # re-read stats fresh: the get("a") above added one miss post-clear.
    st = cache.stats()
    assert st["size"] == 0
    assert st["hits"] == 0
    assert st["misses"] == 1  # only the single post-clear get("a") miss


def test_clear_zeroes_stats_immediately() -> None:
    cache: TtlLruCache[int] = TtlLruCache(maxsize=1, ttl_seconds=100, clock=FakeClock())
    cache.set("a", 1)
    cache.get("a")  # hit
    cache.set("b", 2)  # evicts "a"
    cache.clear()
    assert cache.stats() == {"hits": 0, "misses": 0, "size": 0, "evictions": 0}


def test_stats_counts_hits_misses_evictions() -> None:
    cache: TtlLruCache[int] = TtlLruCache(maxsize=2, ttl_seconds=1000, clock=FakeClock())
    assert cache.get("x") is None  # miss #1
    cache.set("x", 1)
    assert cache.get("x") == 1  # hit #1 (touch -> "x" most-recently-used)
    cache.set("y", 2)  # store: x(LRU), y
    cache.set("z", 3)  # over capacity -> evict LRU == "x"
    assert cache.stats() == {"hits": 1, "misses": 1, "size": 2, "evictions": 1}


def test_decorator_memoizes_on_args() -> None:
    calls: list[int] = []
    cache: TtlLruCache[int] = TtlLruCache(maxsize=8, ttl_seconds=100, clock=FakeClock())

    @cached(cache)
    def square(n: int) -> int:
        """Square a number, recording each real computation."""
        calls.append(n)
        return n * n

    assert square(3) == 9  # computes
    assert square(3) == 9  # memoized -> no recompute
    assert calls == [3]
    assert square(4) == 16  # different arg -> computes
    assert calls == [3, 4]
    # functools.wraps preserves identity/metadata.
    assert square.__name__ == "square"
    assert square.__doc__ == "Square a number, recording each real computation."


def test_decorator_keys_distinguish_positional_and_keyword() -> None:
    seen: list[tuple[int, int]] = []
    cache: TtlLruCache[int] = TtlLruCache(maxsize=8, ttl_seconds=100, clock=FakeClock())

    @cached(cache)
    def add(a: int, b: int) -> int:
        seen.append((a, b))
        return a + b

    assert add(1, 2) == 3
    assert add(1, 2) == 3  # same args -> memoized
    assert add(1, b=2) == 3  # keyword form is a *distinct* key -> recomputes
    assert seen == [(1, 2), (1, 2)]


def test_cache_stats_dataclass_is_frozen_with_as_dict() -> None:
    stats = CacheStats(hits=3, misses=1, size=2, evictions=1)
    assert stats.as_dict() == {"hits": 3, "misses": 1, "size": 2, "evictions": 1}
    with pytest.raises(AttributeError):
        stats.hits = 9  # type: ignore[misc]  # frozen -> immutable


def test_constructor_validates_arguments() -> None:
    with pytest.raises(ValueError, match="maxsize"):
        TtlLruCache(maxsize=0)
    with pytest.raises(ValueError, match="ttl_seconds"):
        TtlLruCache(ttl_seconds=0)

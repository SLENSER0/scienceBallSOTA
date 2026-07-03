"""In-process TTL + LRU retrieval cache — кэш с TTL и вытеснением (§12.11).

The spec (§12.11) caches retrieval results keyed by ``(normalized_query +
filters + mode)`` behind Redis (§13.1) with a *time-to-live* and invalidation on
ingestion-upsert (§9.2 Step 7) so the chat never serves a stale graph. This
module is the **embedded, dependency-free equivalent** of that Redis layer — a
single-process cache used when the deployment profile has no external Redis
(Science-Ball OSS-only / embedded-stores constraint).

Two eviction disciplines run together:

* **TTL (истечение срока)** — every entry remembers the wall-time at which it
  was *stored plus* ``ttl_seconds``. Expiry is *lazy*: a stale entry is dropped
  when it is next touched (``get`` / ``get_or_compute``), counting as a miss —
  **not** an eviction. ``get`` never refreshes the TTL; only ``set`` does.
* **LRU (вытеснение давних)** — the store is capacity-bounded at ``maxsize``.
  When a ``set`` pushes past the bound the *least-recently-used* entry is
  popped and counted as an eviction. Every successful ``get`` / ``set`` marks
  its key most-recently-used.

**Determinism (детерминизм в тестах).** The clock is injectable
(``clock=`` — any zero-arg ``() -> float``; defaults to :func:`time.monotonic`).
Tests advance a fake counter to drive TTL expiry to the exact second, with no
real ``time.sleep`` and no wall-clock dependency.

Public API:

* :class:`CacheStats`  — frozen snapshot of the counters with
  :meth:`CacheStats.as_dict`.
* :class:`TtlLruCache` — the cache: ``get`` / ``set`` / ``get_or_compute`` /
  ``invalidate`` / ``clear`` / ``stats``.
* :func:`cached`       — memoizing decorator keyed on the call arguments.
"""

from __future__ import annotations

import functools
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass

__all__ = [
    "CacheStats",
    "TtlLruCache",
    "cached",
]

# Injectable seams / type aliases (§12.11 «детерминизм»).
type ClockFn = Callable[[], float]
type Key = Hashable

# Defaults mirror a modest chat retrieval-cache (§12.11 / §18 «Slow chat»).
DEFAULT_MAXSIZE = 256
DEFAULT_TTL_SECONDS = 300.0

# Sentinel distinguishing «absent / expired» from a legitimately stored ``None``.
_MISSING = object()


@dataclass(frozen=True, slots=True)
class CacheStats:
    """Immutable snapshot of cache counters — статистика кэша (§12.11).

    ``hits`` / ``misses`` drive the hit-rate the spec asks to observe
    (§12.11 «hit-rate»); ``size`` is the number of *physically* stored entries
    (expired-but-not-yet-touched keys still count until lazily dropped);
    ``evictions`` counts only LRU capacity evictions, never TTL expiries.
    """

    hits: int
    misses: int
    size: int
    evictions: int

    def as_dict(self) -> dict[str, int]:
        """JSON-friendly view — таблица счётчиков (§12.11)."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "size": self.size,
            "evictions": self.evictions,
        }


class TtlLruCache[V]:
    """TTL + LRU in-process cache — кэш ретривала (§12.11).

    ``maxsize`` bounds the number of live entries (LRU eviction past it);
    ``ttl_seconds`` is the per-entry lifetime measured from its last ``set``.
    ``clock`` is any zero-arg ``() -> float`` returning a monotonically
    non-decreasing time; it defaults to :func:`time.monotonic` and is injected
    in tests to make TTL expiry exact and instant.
    """

    def __init__(
        self,
        maxsize: int = DEFAULT_MAXSIZE,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        *,
        clock: ClockFn | None = None,
    ) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        if ttl_seconds <= 0.0:
            raise ValueError("ttl_seconds must be > 0")
        self._maxsize = maxsize
        self._ttl_seconds = ttl_seconds
        self._clock: ClockFn = clock if clock is not None else time.monotonic
        # key -> (value, expiry_time); insertion order == recency (oldest first).
        self._store: OrderedDict[Key, tuple[V, float]] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def _live(self, key: Key) -> V | object:
        """Return the live value or :data:`_MISSING`, applying TTL + LRU touch.

        A present-but-expired entry (``now >= expiry``) is dropped here and
        reported as :data:`_MISSING` (a miss, not an eviction). A live entry is
        moved to the most-recently-used end. Does *not* touch hit/miss counters —
        callers decide, since :meth:`get_or_compute` accounts differently.
        """
        entry = self._store.get(key, _MISSING)
        if entry is _MISSING:
            return _MISSING
        value, expiry = entry  # type: ignore[misc]
        if self._clock() >= expiry:
            del self._store[key]  # истёк срок — lazy TTL expiry
            return _MISSING
        self._store.move_to_end(key)  # mark most-recently-used
        return value

    def get(self, key: Key, default: V | None = None) -> V | None:
        """Return the cached value or ``default`` — чтение из кэша (§12.11).

        A live entry counts as a hit and becomes most-recently-used; an absent
        or TTL-expired entry counts as a miss and ``default`` is returned.
        """
        value = self._live(key)
        if value is _MISSING:
            self._misses += 1
            return default
        self._hits += 1
        return value  # type: ignore[return-value]

    def set(self, key: Key, value: V) -> None:
        """Store ``value`` under ``key`` — запись в кэш (§12.11).

        The entry's TTL is (re)started from *now* and the key becomes
        most-recently-used. If the store then exceeds ``maxsize`` the
        least-recently-used entries are evicted (counted in ``evictions``).
        """
        self._store[key] = (value, self._clock() + self._ttl_seconds)
        self._store.move_to_end(key)
        while len(self._store) > self._maxsize:
            self._store.popitem(last=False)  # drop least-recently-used
            self._evictions += 1

    def get_or_compute(self, key: Key, fn: Callable[[], V]) -> V:
        """Return the cached value, else compute + cache it — «once» (§12.11).

        On a live hit ``fn`` is **not** called (hit counted). On a miss/expiry
        ``fn()`` is computed exactly once, stored (restarting its TTL), and
        returned (miss counted).
        """
        value = self._live(key)
        if value is not _MISSING:
            self._hits += 1
            return value  # type: ignore[return-value]
        self._misses += 1
        computed = fn()
        self.set(key, computed)
        return computed

    def invalidate(self, key: Key) -> bool:
        """Drop ``key`` if present — инвалидация при upsert (§12.11 / §9.2).

        Returns ``True`` if an entry was removed, ``False`` if it was absent.
        Does not affect hit/miss/eviction counters.
        """
        return self._store.pop(key, _MISSING) is not _MISSING

    def clear(self) -> None:
        """Reset the cache fully — сброс кэша (§12.11).

        Removes every entry *and* zeroes all counters, returning the cache to
        its freshly-constructed state.
        """
        self._store.clear()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def stats(self) -> dict[str, int]:
        """Return the counters as a dict — статистика (§12.11 «hit-rate»)."""
        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            size=len(self._store),
            evictions=self._evictions,
        ).as_dict()


def _make_key(qualname: str, args: tuple[object, ...], kwargs: dict[str, object]) -> Key:
    """Build a hashable cache key from a call — ключ по аргументам (§12.11).

    Keyed on the function's qualified name plus positional args and the
    keyword args sorted by name (so call order does not matter). All arguments
    must be hashable — otherwise a :class:`TypeError` propagates on lookup.
    """
    return (qualname, args, tuple(sorted(kwargs.items())))


def cached[V](cache: TtlLruCache[V]) -> Callable[[Callable[..., V]], Callable[..., V]]:
    """Memoize a function through ``cache`` — декоратор мемоизации (§12.11).

    ``@cached(cache)`` routes each call through :meth:`TtlLruCache.get_or_compute`
    with a key derived from the arguments (see :func:`_make_key`), so identical
    calls reuse the cached result within the TTL. Function metadata is preserved
    via :func:`functools.wraps`. Arguments must be hashable.
    """

    def decorator(fn: Callable[..., V]) -> Callable[..., V]:
        @functools.wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> V:
            key = _make_key(fn.__qualname__, args, kwargs)
            return cache.get_or_compute(key, lambda: fn(*args, **kwargs))

        return wrapper

    return decorator

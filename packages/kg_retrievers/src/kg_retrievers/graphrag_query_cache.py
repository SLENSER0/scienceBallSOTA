"""GraphRAG global-search query cache (§11.7 кэш запросов global-search).

Global-search over community reports (отчёты по сообществам) is expensive: the same
question, asked again at the same community ``level`` against the same graph build,
should hit an in-memory cache instead of re-running the map-reduce. This module gives:

* :func:`make_cache_key` — a deterministic ``sha256`` hex over the *normalized*
  (lowercased / stripped) query plus the ``build_version`` (версия сборки графа) and the
  community ``level``, so semantically-identical requests collapse to one key while a
  different level (уровень) or a rebuilt graph gets a fresh key;
* :class:`CacheEntry` — a frozen record of one cached answer with an explicit
  ``expires_at`` (TTL, время жизни) and a JSON-serializable :meth:`~CacheEntry.as_dict`;
* :class:`GlobalSearchCache` — a mutable TTL cache with ``get`` / ``put`` /
  ``evict_expired`` / ``size``, where ``now`` is always injected by the caller so the
  clock is testable (тестируемые часы) and eviction is deterministic.

The cache holds no store handles — it is a plain dict keyed by :func:`make_cache_key` —
so it is cheap to construct, snapshot, and drop between builds.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass


def _normalize_query(query: str) -> str:
    """Normalize a query (нормализованный запрос) for keying: strip then lowercase.

    Case- and surrounding-whitespace differences must not fork the cache, so two
    surface variants of the same question map to one key.
    """
    return query.strip().lower()


def make_cache_key(query: str, build_version: str, level: int) -> str:
    """Deterministic ``sha256`` hex key over (normalized query, build_version, level).

    The three parts are joined with ``\\x00`` so they cannot bleed into each other, then
    hashed; identical inputs always yield the same hex, and any change to the query
    content, the graph ``build_version``, or the community ``level`` changes it.
    """
    normalized = _normalize_query(query)
    payload = "\x00".join((normalized, build_version, str(level)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CacheEntry:
    """One cached global-search answer (§11.7) with its TTL window.

    ``created_at`` / ``expires_at`` are wall-clock-ish floats supplied by the caller;
    the entry is *expired* once ``now >= expires_at``.
    """

    key: str
    value: dict
    created_at: float
    expires_at: float

    def as_dict(self) -> dict:
        """JSON-serializable snapshot (сериализуемый снимок) of this entry."""
        return asdict(self)


class GlobalSearchCache:
    """Mutable in-memory TTL cache for global-search results (§11.7).

    ``ttl_seconds`` is the lifetime applied to every :meth:`put`; the caller injects
    ``now`` on each operation so expiry is deterministic and unit-testable.
    """

    def __init__(self, ttl_seconds: float) -> None:
        self.ttl_seconds: float = ttl_seconds
        self._entries: dict[str, CacheEntry] = {}

    def get(self, key: str, *, now: float) -> dict | None:
        """Return the cached value, or ``None`` if missing or expired (``now >= exp``)."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        if now >= entry.expires_at:
            return None
        return entry.value

    def put(self, key: str, value: dict, *, now: float) -> CacheEntry:
        """Store ``value`` under ``key`` with ``expires_at = now + ttl_seconds``."""
        entry = CacheEntry(
            key=key,
            value=value,
            created_at=now,
            expires_at=now + self.ttl_seconds,
        )
        self._entries[key] = entry
        return entry

    def size(self) -> int:
        """Number of entries currently held (including any not-yet-evicted expired)."""
        return len(self._entries)

    def evict_expired(self, now: float) -> int:
        """Drop every entry with ``now >= expires_at``; return how many were removed."""
        expired = [k for k, e in self._entries.items() if now >= e.expires_at]
        for key in expired:
            del self._entries[key]
        return len(expired)

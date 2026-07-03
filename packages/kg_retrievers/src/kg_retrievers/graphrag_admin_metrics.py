"""GraphRAG admin metrics — build/latency/cache rollup (§11.13).

A small, read-only *reporting* layer that summarises the operational health of the
GraphRAG global-search subsystem for an admin dashboard. It combines three inputs:

- the *active build* (активная сборка) — the community summarisation build currently
  serving queries, carrying its ``build_version``, ``n_communities`` and
  ``created_at`` timestamp (or ``None`` when no build has been materialised yet);
- the *global-search latencies* (задержки) — per-query wall-clock times in
  milliseconds, whose arithmetic mean is the headline latency;
- the *cache stats* (статистика кэша) — ``hits``/``misses`` counters for the
  global-answer cache, from which the hit rate and total search count are derived.

:func:`build_admin_metrics` folds these into a frozen :class:`GraphRagAdminMetrics`.
It is defensive about empty inputs: no latencies yields ``avg_global_latency_ms=0.0``
and a zeroed cache (``hits+misses==0``) yields ``cache_hit_rate=0.0`` without a
division-by-zero. It never touches the graph or any store.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GraphRagAdminMetrics:
    """Operational rollup for the GraphRAG global-search admin view (§11.13).

    ``build_version`` / ``last_rebuild_at`` are ``None`` when no active build exists;
    ``n_communities`` is then ``0``. ``avg_global_latency_ms`` is the mean per-query
    latency (``0.0`` with no samples). ``cache_hit_rate`` is ``hits/(hits+misses)``
    (``0.0`` when the cache is empty) and ``n_searches`` is ``hits+misses``.
    """

    build_version: str | None
    n_communities: int
    last_rebuild_at: str | None
    avg_global_latency_ms: float
    cache_hit_rate: float
    n_searches: int

    def as_dict(self) -> dict:
        return {
            "build_version": self.build_version,
            "n_communities": self.n_communities,
            "last_rebuild_at": self.last_rebuild_at,
            "avg_global_latency_ms": self.avg_global_latency_ms,
            "cache_hit_rate": self.cache_hit_rate,
            "n_searches": self.n_searches,
        }


def build_admin_metrics(
    *,
    active_build: dict | None,
    latencies_ms: list[float],
    cache_stats: dict,
) -> GraphRagAdminMetrics:
    """Fold build/latency/cache inputs into a :class:`GraphRagAdminMetrics` (§11.13).

    ``active_build`` (when present) supplies ``build_version`` / ``n_communities`` /
    ``created_at``; when ``None`` the version and rebuild timestamp are ``None`` and
    ``n_communities`` is ``0``. ``avg_global_latency_ms`` is the arithmetic mean of
    ``latencies_ms`` (``0.0`` if empty). ``cache_hit_rate`` is ``hits/(hits+misses)``
    (``0.0`` when both are ``0``) and ``n_searches`` is ``hits+misses``.
    """
    if active_build is None:
        build_version: str | None = None
        n_communities = 0
        last_rebuild_at: str | None = None
    else:
        build_version = active_build.get("build_version")
        n_communities = int(active_build.get("n_communities", 0))
        last_rebuild_at = active_build.get("created_at")

    avg_global_latency_ms = float(sum(latencies_ms) / len(latencies_ms)) if latencies_ms else 0.0

    hits = int(cache_stats.get("hits", 0))
    misses = int(cache_stats.get("misses", 0))
    n_searches = hits + misses
    cache_hit_rate = hits / n_searches if n_searches else 0.0

    return GraphRagAdminMetrics(
        build_version=build_version,
        n_communities=n_communities,
        last_rebuild_at=last_rebuild_at,
        avg_global_latency_ms=avg_global_latency_ms,
        cache_hit_rate=cache_hit_rate,
        n_searches=n_searches,
    )

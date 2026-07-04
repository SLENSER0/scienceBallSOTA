"""Coverage dashboard: timeline + gaps-by-lab/team endpoint (§15.5 / §5.2.7).

RU: Управленческий срез панели пробелов (§5.2.7 Gap Dashboard) — две панели поверх
уже готовых чистых агрегаторов ``kg_retrievers.coverage_matrix``:

- «динамика покрытия во времени» — ряд по годам публикаций
  (``build_coverage_timeline`` → ``CoverageTimelinePoint``): за каждый год число
  статей, измерений-доказательств и зафиксированных пробелов, плюс производный
  ``coverage_ratio`` = измерения / (измерения + пробелы);
- «у кого не хватает метаданных» — открытые ``Gap`` сгруппированы по владельцу
  (лаборатория / домен) через ``aggregate_gaps_by_owner`` → ``GapByOwner``; сумма
  ``gap_count`` по группам равна общему числу ``Gap`` (полное разбиение).

В отличие от тяжёлого ``/admin/coverage-matrix`` (который дополнительно считает
всю матрицу material × property), этот эндпоинт отдаёт только два лёгких ряда для
дашборда руководителя, без построения полной сетки покрытия.

EN: Management slice of the §5.2.7 Gap Dashboard: a coverage-over-time timeline and a
missing-metadata-by-lab/team breakdown, both built on the existing pure aggregators in
``kg_retrievers.coverage_matrix`` (``build_coverage_timeline`` / ``aggregate_gaps_by_owner``).
Unlike ``/admin/coverage-matrix`` it skips the heavy material×property grid and returns
only the two light series the dashboard needs.

Distinct ``/coverage/dashboard`` path (own router, shared ``/api/v1/coverage`` prefix with
the sibling heatmap/sankey endpoints) so it never collides with ``/gaps`` nor the heavier
``/admin/coverage-matrix``. Strictly read-only: it never mutates the graph. Runs against
the live Neo4j server profile used by the rest of the gap dashboard.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import APIRouter, Query

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/coverage", tags=["coverage"])


def _coverage_ratio(measured: int, gaps: int) -> float:
    """Share of covered items = measurements / (measurements + gaps); 0 when empty."""
    denom = measured + gaps
    return round(measured / denom, 4) if denom else 0.0


# --- TTL memo for the two heavy full-graph aggregators -----------------------
# RU: ``build_coverage_timeline`` делает 3 полных обхода графа, а
# ``aggregate_gaps_by_owner`` — ещё один; единственный параметр ``owner_limit``
# лишь режет уже посчитанный список и на тяжёлый расчёт не влияет. Панель
# руководителя — только чтение, поэтому кэшируем результат обоих агрегаторов
# (points, owners) на короткое TTL-окно, ключ — ``store.db_path`` (одинаков для
# Kuzu и Neo4j). Короткая устареваемость допустима; всё остальное считается как
# и раньше на каждый запрос поверх кэшированных списков.
# EN: build_coverage_timeline runs 3 full-graph traversals and
# aggregate_gaps_by_owner a 4th, while the only query param (owner_limit) merely
# slices an already-computed list. Read-only management dashboard, so memoize the
# (points, owners) tuple per ``store.db_path`` for a short TTL window; the cheap
# per-request derivation (coverage_ratio / summary / ranking / slicing) is
# unchanged and runs on every call over the cached lists.
_CACHE_TTL_SECONDS = 30.0
_cache_lock = threading.Lock()
# db_path -> (expiry_monotonic, (timeline_points, owners))
_cache: dict[str, tuple[float, tuple[list[Any], list[Any]]]] = {}


def _coverage_aggregates(store: Any) -> tuple[list[Any], list[Any]]:
    """Return ``(timeline_points, owners)`` via a short-lived TTL cache (§15.5).

    On a miss, runs the two heavy full-graph aggregators once and memoizes their
    result keyed on ``store.db_path`` for :data:`_CACHE_TTL_SECONDS`; on a hit the
    cached lists are returned verbatim. All per-request derivation stays with the
    caller, so the response is identical within a TTL window (RU: короткое окно
    устаревания на read-only панели).
    """
    from kg_retrievers.coverage_matrix import (
        aggregate_gaps_by_owner,
        build_coverage_timeline,
    )

    key = getattr(store, "db_path", None) or str(id(store))
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]
    # Compute outside the lock (pure, read-only traversals): a concurrent miss at
    # most recomputes redundantly, never returns a torn/partial result.
    points = build_coverage_timeline(store)
    owners = aggregate_gaps_by_owner(store)
    with _cache_lock:
        _cache[key] = (now + _CACHE_TTL_SECONDS, (points, owners))
    return points, owners


@router.get("/dashboard")
def coverage_dashboard(
    owner_limit: int | None = Query(default=None, ge=1, le=500),
) -> dict:
    """Coverage timeline + gaps-by-lab/team for the Gap Dashboard (§15.5 / §5.2.7).

    Reuses ``build_coverage_timeline`` (year-ordered paper / measurement / gap counts)
    and ``aggregate_gaps_by_owner`` (open ``Gap`` nodes partitioned by owning lab /
    domain). ``owner_limit`` optionally caps the by-owner list to the worst offenders
    (largest ``gap_count`` first) for the dashboard, without dropping them from the
    totals. Each timeline point gains a derived ``coverage_ratio``; the response also
    carries a roll-up ``summary`` for the dashboard header.
    """
    store = get_store()

    # Heavy full-graph aggregates (Panel 1 + Panel 2) come from a short TTL cache;
    # everything below is cheap pure-Python derivation over the cached lists.
    points, owners = _coverage_aggregates(store)

    # --- Panel 1: coverage over time (year buckets, ascending) ---------------
    timeline: list[dict[str, Any]] = []
    total_papers = 0
    total_measured = 0
    total_gaps_timeline = 0
    for p in points:
        total_papers += p.paper_count
        total_measured += p.measurement_count
        total_gaps_timeline += p.gap_count
        entry = p.as_dict()
        entry["coverage_ratio"] = _coverage_ratio(p.measurement_count, p.gap_count)
        timeline.append(entry)

    # --- Panel 2: missing metadata by owner (lab / team / domain) ------------
    total_gaps = sum(g.gap_count for g in owners)
    # Worst offenders first (most missing metadata), then stable by owner key.
    ranked = sorted(owners, key=lambda g: (-g.gap_count, g.owner))
    by_owner_all = [g.as_dict() for g in ranked]
    by_owner = by_owner_all[:owner_limit] if owner_limit is not None else by_owner_all
    unassigned = next(
        (g.gap_count for g in owners if g.owner == "unassigned"),
        0,
    )

    return {
        "timeline": timeline,
        "by_owner": by_owner,
        "summary": {
            "years": len(timeline),
            "papers": total_papers,
            "measurements": total_measured,
            "gaps_dated": total_gaps_timeline,
            "gaps_total": total_gaps,
            "owners": len(owners),
            "unassigned_gaps": unassigned,
            "shown_owners": len(by_owner),
        },
    }

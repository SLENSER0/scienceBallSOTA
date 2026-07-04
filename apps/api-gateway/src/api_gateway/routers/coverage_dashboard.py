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

from typing import Any

from fastapi import APIRouter, Query

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/coverage", tags=["coverage"])


def _coverage_ratio(measured: int, gaps: int) -> float:
    """Share of covered items = measurements / (measurements + gaps); 0 when empty."""
    denom = measured + gaps
    return round(measured / denom, 4) if denom else 0.0


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
    from kg_retrievers.coverage_matrix import (
        aggregate_gaps_by_owner,
        build_coverage_timeline,
    )

    store = get_store()

    # --- Panel 1: coverage over time (year buckets, ascending) ---------------
    points = build_coverage_timeline(store)
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
    owners = aggregate_gaps_by_owner(store)
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

"""ER observability metrics for ``/admin/metrics`` (§8.13).

Surfaces the entity-resolution quality counters the roadmap (§8.13) asks the
admin metrics surface to expose:

* ``er_candidates_total``      — total merge candidates (multi-member groups)
* ``er_auto_merge_total``      — groups the decision engine would auto-merge
* ``er_review_needed_total``   — groups routed to human review
* ``er_separate_total``        — groups the engine keeps apart
* ``er_blocked_overwrite_total`` — merges blocked because they touch a
  reviewed/locked canonical (§8.9 protection)
* ``er_model_version``         — version of the ``kg_er`` resolver + fixed seed
* ``er_last_run_ts``           — unix ts of this metrics computation

The numbers are computed live: the same :func:`kg_er.resolve` pipeline that
powers the ER review screen (§8.8, ``routers/er_candidates.py``) is run over the
current canonical nodes of every supported entity type, and its proposals are
tallied by decision. Nothing is persisted — the counters always reflect the
graph as it stands, so after an ingestion run ``GET /admin/er-metrics`` returns
non-zero ER counters (the §8.13 acceptance condition).

Two exposition formats, matching the built-in ``/admin/metrics`` route:

* ``GET /api/v1/admin/er-metrics``                    → JSON
* ``GET /api/v1/admin/er-metrics?format=prometheus``  → Prometheus text (§14.11)

The Prometheus body is rendered with the stdlib renderer in
``api_gateway.prometheus_text`` so it can be scraped alongside the core metrics.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from api_gateway.deps import get_store
from api_gateway.prometheus_text import MetricFamily, Sample, render_exposition

# Reuse the exact mention field-mapping + node cap the ER review endpoint uses
# (§8.8) so the resolver sees identical inputs on both surfaces.
from api_gateway.routers.er_candidates import _SUPPORTED_TYPES, _mention_dicts

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_REVIEWED_STATES = {"accepted", "corrected"}


class ERTypeMetrics(BaseModel):
    """Per-entity-type ER decision breakdown (§8.13)."""

    entity_type: str
    n_input: int
    candidates_total: int
    auto_merge_total: int
    review_needed_total: int
    separate_total: int
    blocked_overwrite_total: int
    backend: str


class ERMetricsResponse(BaseModel):
    """Aggregated ER observability counters for ``/admin/metrics`` (§8.13)."""

    er_candidates_total: int
    er_auto_merge_total: int
    er_review_needed_total: int
    er_separate_total: int
    er_blocked_overwrite_total: int
    er_model_version: str
    er_random_seed: int
    er_last_run_ts: float
    by_type: list[ERTypeMetrics]


def _model_version() -> tuple[str, int]:
    """``(version_string, random_seed)`` for the live ER resolver (§8.4/§8.13)."""
    try:
        from kg_er import __version__ as er_version
    except Exception:
        er_version = "unknown"
    seed = -1
    try:
        from kg_er.models.base import RANDOM_SEED

        seed = int(RANDOM_SEED)
    except Exception:
        pass
    return f"kg_er-{er_version}", seed


def _resolve_type(store: Any, entity_type: str) -> ERTypeMetrics:
    """Run :func:`kg_er.resolve` for one type and tally its proposals by decision."""
    mentions = _mention_dicts(store, entity_type)
    counts = {"auto_merge": 0, "review_needed": 0, "separate": 0}
    blocked = 0
    total = 0
    backend = "trivial"

    if len(mentions) >= 2:
        from kg_er import resolve  # lazy: heavy Splink/duckdb import

        reviewed = frozenset(
            m["unique_id"]
            for m in mentions
            if m.get("_review_status") in _REVIEWED_STATES
        )
        try:
            result = resolve(entity_type, mentions, reviewed_ids=reviewed)
            backend = str(result.model_card.get("backend", "unknown"))
            for p in result.proposals:
                total += 1
                decision = p.decision.value
                if decision in counts:
                    counts[decision] += 1
                if p.blocked_by_review:
                    blocked += 1
        except Exception:  # ER must never 500 the metrics surface
            backend = "error"

    return ERTypeMetrics(
        entity_type=entity_type,
        n_input=len(mentions),
        candidates_total=total,
        auto_merge_total=counts["auto_merge"],
        review_needed_total=counts["review_needed"],
        separate_total=counts["separate"],
        blocked_overwrite_total=blocked,
        backend=backend,
    )


def _compute() -> ERMetricsResponse:
    store = get_store()
    version, seed = _model_version()
    by_type = [_resolve_type(store, t) for t in _SUPPORTED_TYPES]
    return ERMetricsResponse(
        er_candidates_total=sum(t.candidates_total for t in by_type),
        er_auto_merge_total=sum(t.auto_merge_total for t in by_type),
        er_review_needed_total=sum(t.review_needed_total for t in by_type),
        er_separate_total=sum(t.separate_total for t in by_type),
        er_blocked_overwrite_total=sum(t.blocked_overwrite_total for t in by_type),
        er_model_version=version,
        er_random_seed=seed,
        er_last_run_ts=round(time.time(), 3),
        by_type=by_type,
    )


def _prometheus(m: ERMetricsResponse) -> str:
    """Render the ER counters as a Prometheus exposition body (§14.11/§8.13).

    One aggregate sample per counter plus a per-``entity_type`` breakdown, and a
    labelled ``er_model_version`` info gauge carrying the resolver version + seed.
    """

    def counter(name: str, help_: str, agg: int, field: str) -> MetricFamily:
        samples = [Sample(name, float(agg))]
        samples.extend(
            Sample(name, float(getattr(t, field)), {"entity_type": t.entity_type})
            for t in m.by_type
        )
        return MetricFamily(name, "counter", help_, tuple(samples))

    families = [
        counter("er_candidates_total", "ER merge candidates (multi-member groups)",
                m.er_candidates_total, "candidates_total"),
        counter("er_auto_merge_total", "ER groups decided auto_merge",
                m.er_auto_merge_total, "auto_merge_total"),
        counter("er_review_needed_total", "ER groups routed to review",
                m.er_review_needed_total, "review_needed_total"),
        counter("er_separate_total", "ER groups kept separate",
                m.er_separate_total, "separate_total"),
        counter("er_blocked_overwrite_total", "ER merges blocked by reviewed-canonical protection",
                m.er_blocked_overwrite_total, "blocked_overwrite_total"),
        MetricFamily(
            "er_model_version",
            "gauge",
            "ER resolver model version + fixed seed (info metric, value always 1)",
            (Sample("er_model_version", 1.0,
                    {"version": m.er_model_version, "seed": str(m.er_random_seed)}),),
        ),
        MetricFamily(
            "er_last_run_ts",
            "gauge",
            "Unix timestamp of the last ER metrics computation",
            (Sample("er_last_run_ts", m.er_last_run_ts),),
        ),
    ]
    return render_exposition(families)


@router.get("/er-metrics")
def er_metrics(format: str = Query(default="json")) -> Any:
    """ER observability counters for ``/admin/metrics`` (§8.13).

    ``format=prometheus`` returns a scrapeable text exposition; the default JSON
    body carries the aggregate counters plus a per-entity-type breakdown.
    """
    metrics = _compute()
    if format == "prometheus":
        return PlainTextResponse(
            _prometheus(metrics), media_type="text/plain; version=0.0.4"
        )
    return metrics

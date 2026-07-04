"""End-to-end pipeline-lineage & traceable-run emission (§10.5).

§10.5 asks for the *real* Dagster ingestion lineage — the canonical §9.1 asset
graph from ``RAW → source → parsed → chunks → triples → normalized → resolved →
Neo4j KG + Qdrant + OpenSearch`` — together with **run-level metadata** for every
traceable pipeline прогон: ``job_id``, terminal status, duration and the volume
counters (documents / chunks / triples) plus the extractor/model that produced
them. That backbone is what §10.7 (source-catalog UI) and the Phase-8 acceptance
«каждый pipeline-run трассируем» build on.

This router does **not** re-implement any of that logic — it wires together the
pure building blocks already vendored in ``kg_common.metadata``:

* :mod:`kg_common.metadata.pipeline_lineage_spec` — the fixed twelve-step §9.1
  DAG (``StepSpec`` inputs→outputs, dataset lineage edges, terminal serving stores).
* :mod:`kg_common.metadata.lineage_topology` — Kahn topo-order / source / sink /
  cycle analysis over the emitted edge list.
* :mod:`kg_common.metadata.pipeline_run_facts` — normalized run projection
  (``RunFacts``) and cross-run ``rollup`` (success rate + total counters).
* :mod:`kg_common.metadata.pipeline_failure_impact` — blast-radius of a failed
  step (which serving stores are left un-refreshed).

The *real, traceable runs* are read from the live server-profile graph store on
:8000 — every ``ExtractorRun`` / ``GapScanRun`` node the migrated Neo4j already
carries — and, when present, merged with the SQL ``RunRegistry`` (``pipeline_runs``
table) which additionally supplies status / started-at / finished-at → duration.
Counters are derived from the graph itself (nodes stamped with the run's
``extractor_run_id``), so the numbers are the graph's own truth, not a mock.

Endpoints (prefix ``/api/v1/pipeline-lineage``):

* ``GET /graph``                — canonical §9.1 lineage DAG + topology.
* ``GET /runs``                 — traceable runs (facts) + cross-run rollup.
* ``GET /runs/{run_id}``        — one run's facts + its lineage graph.
* ``GET /failure-impact/{step}``— blast radius of a hypothetically failed step.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_gateway.deps import get_store
from kg_common import get_settings
from kg_common.metadata.lineage_topology import analyze
from kg_common.metadata.pipeline_failure_impact import impact
from kg_common.metadata.pipeline_lineage_spec import (
    PIPELINE_STEPS,
    lineage_edges,
    terminal_outputs,
)
from kg_common.metadata.pipeline_run_facts import from_run, rollup

router = APIRouter(prefix="/api/v1/pipeline-lineage", tags=["pipeline-lineage"])

# --- graph-store label → RunFacts counter mapping ---------------------------
# Nodes stamped with a run's ``extractor_run_id`` are grouped by their label; we
# roll those groups into the three §10.5 volume counters.
_DOC_LABELS = ("Document", "Paper", "Source")
_CHUNK_LABELS = ("Chunk",)
_TRIPLE_LABELS = ("Measurement", "Claim", "Finding", "Evidence")

# SQL ``RunRegistry`` lifecycle statuses → the upper-cased RunFacts status set.
_STATUS_MAP = {
    "succeeded": "SUCCESS",
    "success": "SUCCESS",
    "failed": "FAILED",
    "cancelled": "FAILED",
    "canceled": "FAILED",
    "running": "RUNNING",
}


def _lineage_graph() -> dict[str, Any]:
    """Return the canonical §9.1 lineage DAG + its topology — единый источник графа."""
    edges = lineage_edges()
    topo = analyze(edges)
    return {
        "steps": [step.as_dict() for step in PIPELINE_STEPS],
        "edges": [{"source": src, "target": dst} for src, dst in edges],
        "terminal_outputs": sorted(terminal_outputs()),
        "topology": topo.as_dict(),
    }


def _duration_seconds(started_at: str | None, finished_at: str | None) -> float:
    """Wall-clock seconds between two ISO-8601 timestamps (``0.0`` when unknown)."""
    if not started_at or not finished_at:
        return 0.0
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(finished_at)
    except ValueError:
        return 0.0
    delta = (end - start).total_seconds()
    return delta if delta > 0.0 else 0.0


def _graph_runs(store: Any) -> list[dict[str, Any]]:
    """Project every live ``ExtractorRun`` / ``GapScanRun`` node into a raw run mapping.

    Counters are read straight from the graph: nodes carrying this run's
    ``extractor_run_id`` are grouped by label and folded into documents / chunks /
    triples. Such persisted runs are, by construction, ``SUCCESS`` — они уже записаны.
    """
    header = store.rows(
        "MATCH (r:Node) WHERE r.label IN ['ExtractorRun','GapScanRun'] "
        "RETURN r.id, r.label, r.name, r.created_at ORDER BY r.created_at DESC"
    )
    runs: list[dict[str, Any]] = []
    for rid, label, name, created in header:
        by_label: dict[str, int] = {}
        for lbl, cnt in store.rows(
            "MATCH (n:Node) WHERE n.extractor_run_id=$id RETURN n.label, count(n)",
            {"id": rid},
        ):
            if lbl is not None:
                by_label[str(lbl)] = int(cnt)
        runs.append(
            {
                "job_id": str(rid),
                "status": "SUCCESS",
                "duration_s": 0.0,
                "n_documents": sum(by_label.get(x, 0) for x in _DOC_LABELS),
                "n_chunks": sum(by_label.get(x, 0) for x in _CHUNK_LABELS),
                "n_triples": sum(by_label.get(x, 0) for x in _TRIPLE_LABELS),
                "extractor": str(name or ""),
                "model": "",
                "created_at": str(created or ""),
                "run_type": str(label or "ExtractorRun"),
                "source": "graph",
                "by_label": by_label,
            }
        )
    return runs


def _registry_runs() -> list[dict[str, Any]]:
    """Merge in SQL ``RunRegistry`` runs (status / duration) — graceful if absent.

    Any error (no table, unreachable DB, missing package) is swallowed: the graph
    store already supplies real runs, the registry is an enrichment, not a hard dep.
    """
    settings = get_settings()
    if getattr(settings, "runtime_profile", "embedded") == "server":
        url = settings.postgres_dsn
    else:
        url = f"sqlite:///{settings.runtime_dir}/runs.db"
    try:
        from kg_common.storage.run_registry import RunRegistry

        registry = RunRegistry(url)
        recent = registry.recent(limit=100)
    except Exception:  # pragma: no cover - enrichment only, never fatal
        return []

    runs: list[dict[str, Any]] = []
    for run in recent:
        stats = run.stats or {}
        runs.append(
            {
                "job_id": run.run_id,
                "status": _STATUS_MAP.get(run.status, "RUNNING"),
                "duration_s": _duration_seconds(run.started_at, run.finished_at),
                "n_documents": int(stats.get("n_documents", stats.get("documents", 0))),
                "n_chunks": int(stats.get("n_chunks", stats.get("chunks", 0))),
                "n_triples": int(stats.get("n_triples", stats.get("triples", 0))),
                "extractor": str(stats.get("extractor", run.kind or "")),
                "model": str(stats.get("model", "")),
                "created_at": run.started_at or "",
                "run_type": run.kind or "pipeline",
                "source": "registry",
                "failed_step": str(stats.get("failed_step", "")),
                "error": str(stats.get("error", "")),
            }
        )
    return runs


def _collect_runs() -> list[dict[str, Any]]:
    """Union of graph runs and registry runs, de-duplicated by ``job_id``.

    Registry rows win on collision — they carry the richer status/duration that the
    graph projection cannot know. Ordered by ``created_at`` descending, newest first.
    """
    merged: dict[str, dict[str, Any]] = {}
    for raw in _graph_runs(get_store()):
        merged[raw["job_id"]] = raw
    for raw in _registry_runs():
        existing = merged.get(raw["job_id"])
        if existing is not None:
            # keep graph-derived counters when the registry omitted them
            for key in ("n_documents", "n_chunks", "n_triples"):
                if not raw.get(key) and existing.get(key):
                    raw[key] = existing[key]
            raw.setdefault("by_label", existing.get("by_label", {}))
        merged[raw["job_id"]] = raw
    return sorted(merged.values(), key=lambda r: r.get("created_at", ""), reverse=True)


@router.get("/graph")
def graph() -> dict[str, Any]:
    """Canonical §9.1 end-to-end lineage DAG (inputs→outputs) + topology (§10.5)."""
    return _lineage_graph()


@router.get("/runs")
def runs(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
    """Traceable pipeline runs with run-level metadata + cross-run rollup (§10.5).

    Each run is projected through :func:`pipeline_run_facts.from_run` (job_id, status,
    duration, counters, extractor/model) and the whole set is summarised by
    :func:`pipeline_run_facts.rollup` (n_runs, totals, success_rate).
    """
    raw_runs = _collect_runs()[:limit]
    facts = []
    enriched: list[dict[str, Any]] = []
    for raw in raw_runs:
        fact = from_run(raw)
        facts.append(fact)
        row = fact.as_dict()
        row["created_at"] = raw.get("created_at", "")
        row["run_type"] = raw.get("run_type", "")
        row["source"] = raw.get("source", "")
        if raw.get("failed_step"):
            row["failed_step"] = raw["failed_step"]
        if raw.get("error"):
            row["error"] = raw["error"]
        enriched.append(row)
    return {"runs": enriched, "rollup": rollup(facts)}


@router.get("/runs/{run_id}")
def run_detail(run_id: str) -> dict[str, Any]:
    """One run's facts + the lineage graph it materialises; failure blast-radius if FAILED."""
    match = next((r for r in _collect_runs() if r["job_id"] == run_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"unknown run: {run_id}")
    fact = from_run(match)
    detail: dict[str, Any] = {
        "run": {
            **fact.as_dict(),
            "created_at": match.get("created_at", ""),
            "run_type": match.get("run_type", ""),
            "source": match.get("source", ""),
            "by_label": match.get("by_label", {}),
        },
        "lineage": _lineage_graph(),
    }
    if fact.status == "FAILED":
        failed_step = match.get("failed_step") or "extract"
        try:
            detail["failure_impact"] = impact(failed_step).as_dict()
        except ValueError:
            detail["failure_impact"] = impact("extract").as_dict()
    return detail


@router.get("/failure-impact/{step}")
def failure_impact(step: str) -> dict[str, Any]:
    """Blast radius of a hypothetically failed §9.1 step — радиус поражения (§10.5)."""
    try:
        return impact(step).as_dict()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

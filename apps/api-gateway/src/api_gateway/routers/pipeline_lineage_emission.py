"""OpenLineage emission of real §9.1 pipeline runs — эмиссия lineage-событий (§10.5).

§10.5 (« Реальная эмиссия pipeline-lineage из Dagster, end-to-end inputs→outputs »)
requires that every ingestion прогон be **emitted** as a traceable lineage graph —
one OpenLineage ``RunEvent`` per §9.1 step, carrying ``job_id``, status, duration and
the volume counters, with the inputs→outputs dataset edges a catalog (Marquez /
DataHub via ``openlineage-dagster``) reconstructs the pipeline from. The sibling
``pipeline_lineage`` router serves the *read/topology* side; this router serves the
*emission* side.

It performs no emission logic of its own — that lives in the pure, deterministic
:mod:`kg_common.metadata.pipeline_lineage_emitter`. The router only (1) reads the
**real, traceable runs** from the live server-profile graph store on :8000 (every
``ExtractorRun`` / ``GapScanRun`` node the migrated Neo4j carries), enriched — when
present — with the SQL ``RunRegistry`` for status / duration / failed-step, and
(2) hands each run to the emitter. Counters are the graph's own truth (nodes stamped
with the run's ``extractor_run_id``), never a mock.

Endpoints (prefix ``/api/v1/pipeline-lineage-emission``):

* ``GET /catalog``              — static §9.1 job/dataset OpenLineage catalog.
* ``GET /runs``                 — traceable runs available for emission (facts only).
* ``GET /runs/{run_id}/events`` — the full OpenLineage event set for one real run.
* ``GET /preview``              — emit a synthetic run (works with an empty graph),
  parameterised by ``status`` / ``failed_step`` to demo SUCCESS / FAILED semantics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_gateway.deps import get_store
from kg_common import get_settings
from kg_common.metadata.pipeline_lineage_emitter import emit_run, job_catalog
from kg_common.metadata.pipeline_lineage_spec import PIPELINE_STEPS
from kg_common.metadata.pipeline_run_facts import VALID_STATUSES

router = APIRouter(
    prefix="/api/v1/pipeline-lineage-emission",
    tags=["pipeline-lineage-emission"],
)

# graph-store label → RunFacts counter grouping (mirrors the read-side router).
_DOC_LABELS = ("Document", "Paper", "Source")
_CHUNK_LABELS = ("Chunk",)
_TRIPLE_LABELS = ("Measurement", "Claim", "Finding", "Evidence")

# SQL ``RunRegistry`` lifecycle → RunFacts status set.
_STATUS_MAP = {
    "succeeded": "SUCCESS",
    "success": "SUCCESS",
    "failed": "FAILED",
    "cancelled": "FAILED",
    "canceled": "FAILED",
    "running": "RUNNING",
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


def _graph_runs(store: Any) -> dict[str, dict[str, Any]]:
    """Project live ``ExtractorRun`` / ``GapScanRun`` nodes into raw run mappings.

    Counters come straight from the graph — nodes carrying the run's
    ``extractor_run_id`` grouped by label. Persisted graph runs are ``SUCCESS`` by
    construction (they are already written). Keyed by ``job_id``.
    """
    runs: dict[str, dict[str, Any]] = {}
    header = store.rows(
        "MATCH (r:Node) WHERE r.label IN ['ExtractorRun','GapScanRun'] "
        "RETURN r.id, r.label, r.name, r.created_at ORDER BY r.created_at DESC"
    )
    for rid, label, name, created in header:
        by_label: dict[str, int] = {}
        for lbl, cnt in store.rows(
            "MATCH (n:Node) WHERE n.extractor_run_id=$id RETURN n.label, count(n)",
            {"id": rid},
        ):
            if lbl is not None:
                by_label[str(lbl)] = int(cnt)
        runs[str(rid)] = {
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
    return runs


def _registry_runs() -> dict[str, dict[str, Any]]:
    """Merge in SQL ``RunRegistry`` runs (status / duration / failed_step) — best-effort.

    Any failure (missing table, unreachable DB) is swallowed: the graph store already
    provides real runs; the registry is enrichment, never a hard dependency.
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
        return {}

    runs: dict[str, dict[str, Any]] = {}
    for run in recent:
        stats = run.stats or {}
        runs[run.run_id] = {
            "job_id": run.run_id,
            "status": _STATUS_MAP.get(run.status, "RUNNING"),
            "duration_s": _duration_seconds(run.started_at, run.finished_at),
            "n_documents": int(stats.get("n_documents", stats.get("documents", 0))),
            "n_chunks": int(stats.get("n_chunks", stats.get("chunks", 0))),
            "n_triples": int(stats.get("n_triples", stats.get("triples", 0))),
            "extractor": str(stats.get("extractor", run.kind or "")),
            "model": str(stats.get("model", "")),
            "created_at": run.started_at or "",
            "started_at": run.started_at or "",
            "finished_at": run.finished_at or "",
            "run_type": run.kind or "pipeline",
            "source": "registry",
            "failed_step": str(stats.get("failed_step", "")),
        }
    return runs


def _collect_runs() -> list[dict[str, Any]]:
    """Union of graph + registry runs, registry winning on collision — сбор прогонов.

    Registry rows carry the richer status/duration/failed-step; when they omit the
    volume counters, the graph-derived counters are preserved. Newest first.
    """
    merged: dict[str, dict[str, Any]] = _graph_runs(get_store())
    for job_id, raw in _registry_runs().items():
        existing = merged.get(job_id)
        if existing is not None:
            for key in ("n_documents", "n_chunks", "n_triples"):
                if not raw.get(key) and existing.get(key):
                    raw[key] = existing[key]
            raw.setdefault("by_label", existing.get("by_label", {}))
        merged[job_id] = raw
    return sorted(merged.values(), key=lambda r: r.get("created_at", ""), reverse=True)


@router.get("/catalog")
def catalog() -> dict[str, Any]:
    """Static §9.1 job/dataset OpenLineage catalog (run-independent) — каталог (§10.5)."""
    return job_catalog()


@router.get("/runs")
def runs(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
    """Traceable runs available for emission — прогоны для эмиссии (facts only, §10.5)."""
    collected = _collect_runs()[:limit]
    return {
        "runs": [
            {
                "job_id": r["job_id"],
                "status": r["status"],
                "duration_s": r.get("duration_s", 0.0),
                "n_documents": r.get("n_documents", 0),
                "n_chunks": r.get("n_chunks", 0),
                "n_triples": r.get("n_triples", 0),
                "extractor": r.get("extractor", ""),
                "created_at": r.get("created_at", ""),
                "run_type": r.get("run_type", ""),
                "source": r.get("source", ""),
            }
            for r in collected
        ],
        "count": len(collected),
    }


@router.get("/runs/{run_id}/events")
def run_events(run_id: str) -> dict[str, Any]:
    """Emit the full OpenLineage event set for one real run — эмиссия событий прогона (§10.5)."""
    match = next((r for r in _collect_runs() if r["job_id"] == run_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"unknown run: {run_id}")
    envelope = emit_run(match)
    envelope["by_label"] = match.get("by_label", {})
    envelope["run_type"] = match.get("run_type", "")
    envelope["created_at"] = match.get("created_at", "")
    return envelope


@router.get("/preview")
def preview(
    status: str = Query(default="SUCCESS"),
    failed_step: str = Query(default="extract"),
) -> dict[str, Any]:
    """Emit a synthetic run to demo the emission shape — предпросмотр эмиссии (§10.5).

    Works even against an empty graph. ``status`` is one of SUCCESS / FAILED / RUNNING;
    for FAILED, ``failed_step`` selects the failure point so the FAIL/ABORT/COMPLETE
    split is visible without needing a real failed run in the registry.
    """
    norm = status.upper()
    if norm not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {sorted(VALID_STATUSES)}",
        )
    valid_steps = {step.name for step in PIPELINE_STEPS}
    if norm == "FAILED" and failed_step not in valid_steps:
        raise HTTPException(status_code=422, detail=f"unknown step: {failed_step}")
    demo: dict[str, Any] = {
        "job_id": f"preview-{norm.lower()}",
        "status": norm,
        "duration_s": 12.5,
        "n_documents": 3,
        "n_chunks": 128,
        "n_triples": 512,
        "extractor": "gliner-mine-v1",
        "model": "gliner_medium-v2.1",
    }
    if norm == "FAILED":
        demo["failed_step"] = failed_step
    return emit_run(demo)

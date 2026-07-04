"""Live MLflow tracking surface: experiments / runs / params / metrics (§18.4).

Делает воспроизводимость видимой на демо, не требуя поднятого docker-сервиса
mlflow. Хелперы уже готовы (``kg_common.mlflow_utils`` +
``kg_eval.mlflow_experiments`` — реестр трёх экспериментов extraction/retrieval/
answer с ожидаемыми params/metrics §15.2); здесь не хватало *развёрнутого сервиса*
поверх них. Этот роутер и есть тот сервис:

* ``GET  /api/v1/mlflow/status``       — статус tracking-бэкенда: сконфигурирован ли
  ``MLFLOW_TRACKING_URI``, доступен ли клиент mlflow, режим ``server``|``offline``,
  ссылка на MLflow UI (когда сервер поднят).
* ``GET  /api/v1/mlflow/experiments``  — три эксперимента с их schema (ожидаемые
  ``tracked_params``/``tracked_metrics``) и числом прогонов.
* ``GET  /api/v1/mlflow/runs``         — прогоны (params, метрики §15.2, теги
  ``git_sha``/``dataset_version``/``trace_id``), из реального MLflow-сервера если он
  подключён, иначе из локального журнала прогонов, который пишут ``/track*``.
* ``POST /api/v1/mlflow/track/retrieval`` — ЖИВОЙ прогон retrieval-eval над графом
  (``kg_eval.retrieval_eval.run_retrieval_eval``, Recall@10 / MRR / Precision@10 /
  nDCG §18.6/§18.7), лог в MLflow (сервер или офлайн-фоллбэк) и в журнал.
* ``POST /api/v1/mlflow/track/extraction`` — реальные graph-derived метрики качества
  извлечения (evidence-coverage §8.3, avg confidence, счётчики), лог в experiment
  ``extraction``.
* ``POST /api/v1/mlflow/track``          — общий ingest прогона ``{experiment, params,
  metrics}`` для внешних оценщиков (``kg-eval run``, agent answer-runs).

Каждый прогон помечается ``git_sha`` + ``dataset_version`` (детерминированный
fingerprint живого графа) и ``trace_id`` для перехода метрики→трейс — ровно
критерий приёмки §18.4. Всё работает офлайн: при отсутствии/недоступности mlflow
трекинг откатывается на :class:`~kg_common.mlflow_utils.InMemoryRecorder`, а
прогоны сохраняются в JSONL-журнал ``<artifacts_dir>/mlflow_runs.jsonl``, дедуп по
детерминированному ``run_id``.
"""

from __future__ import annotations

import functools
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api_gateway.auth import current_role
from api_gateway.deps import get_store
from kg_common import get_settings
from kg_common.mlflow_utils import EXPERIMENTS, start_run
from kg_eval.mlflow_experiments import (
    ALL_SPECS,
    ANSWER_EXPERIMENT,
    EXTRACTION_EXPERIMENT,
    RETRIEVAL_EXPERIMENT,
)

router = APIRouter(prefix="/api/v1/mlflow", tags=["mlflow"])

_RUNS_FILE = "mlflow_runs.jsonl"
_DEFAULT_K = 10


# -- provenance helpers ---------------------------------------------------
@functools.lru_cache(maxsize=1)
def _git_sha() -> str:
    """Short git SHA of the running tree (``""`` if git is unavailable)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[5]),
            capture_output=True,
            text=True,
            timeout=3,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def _dataset_version(store: Any) -> str:
    """Deterministic fingerprint of the live graph → a stable ``dataset_version``.

    Same corpus (same per-label node counts + edge count) ⇒ same version, so
    re-runs over an unchanged graph land on the same deterministic ``run_id``.
    """
    counts = store.counts()
    nodes, rels = int(counts.get("nodes", 0)), int(counts.get("rels", 0))
    try:
        by_label = store.counts_by_label()
    except Exception:
        by_label = {}
    payload = json.dumps(
        {"n": nodes, "r": rels, "labels": sorted(by_label.items())},
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]
    return f"corpus-{nodes}n-{rels}r-{digest}"


# -- local run journal (offline fallback + demo persistence) --------------
def _runs_path() -> Path:
    s = get_settings()
    root = Path(s.artifacts_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / _RUNS_FILE


def _load_local_runs() -> list[dict[str, Any]]:
    """Read the JSONL run journal, deduped by ``run_id`` (last write wins)."""
    path = _runs_path()
    if not path.exists():
        return []
    latest: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = str(rec.get("run_id", ""))
        if rid:
            latest[rid] = rec
    return list(latest.values())


def _append_local_run(record: dict[str, Any]) -> None:
    with _runs_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# -- mlflow tracking-server status/read -----------------------------------
def _mlflow_available() -> bool:
    try:
        import mlflow  # noqa: F401

        return True
    except Exception:
        return False


def _server_status() -> dict[str, Any]:
    """Describe the tracking backend: server vs offline in-memory fallback."""
    uri = (get_settings().mlflow_tracking_uri or "").strip()
    available = _mlflow_available()
    is_http = uri.startswith("http://") or uri.startswith("https://")
    mode = "server" if (uri and available) else "offline"
    return {
        "mode": mode,
        "tracking_uri": uri,
        "mlflow_installed": available,
        "configured": bool(uri),
        "ui_url": uri if is_http else "",
        "experiments": list(EXPERIMENTS),
    }


def _server_runs(experiment: str | None) -> list[dict[str, Any]]:
    """Fetch runs from a live MLflow tracking server (empty on any failure)."""
    status = _server_status()
    if status["mode"] != "server":
        return []
    try:
        import mlflow
        from mlflow.tracking import MlflowClient

        mlflow.set_tracking_uri(status["tracking_uri"])
        client = MlflowClient()
        wanted = [experiment] if experiment else list(EXPERIMENTS)
        out: list[dict[str, Any]] = []
        for name in wanted:
            exp = client.get_experiment_by_name(name)
            if exp is None:
                continue
            for run in client.search_runs([exp.experiment_id], max_results=200):
                data, info = run.data, run.info
                tags = {k: v for k, v in dict(data.tags).items() if not k.startswith("mlflow.")}
                out.append(
                    {
                        "run_id": info.run_id,
                        "experiment": name,
                        "params": dict(data.params),
                        "metrics": {k: float(v) for k, v in dict(data.metrics).items()},
                        "tags": tags,
                        "git_sha": tags.get("git_sha", ""),
                        "dataset_version": tags.get("dataset_version", ""),
                        "start_time": int(info.start_time or 0),
                        "source": "server",
                    }
                )
        return out
    except Exception:
        return []


# -- shared logging path --------------------------------------------------
def _track(
    experiment: str,
    params: dict[str, Any],
    metrics: dict[str, float],
    *,
    store: Any,
    extra_tags: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Open a tracked run, log params+metrics+provenance, persist and return it.

    Uses real mlflow when ``MLFLOW_TRACKING_URI`` is set and importable, else the
    offline in-memory recorder; either way the snapshot is written to the local
    JSONL journal so the runs list survives without a server.
    """
    if experiment not in EXPERIMENTS:
        raise HTTPException(status_code=400, detail=f"unknown experiment {experiment!r}")
    sha = _git_sha()
    dsv = _dataset_version(store)
    handle = start_run(experiment, git_sha=sha, dataset_version=dsv)
    trace_id = f"trace-{handle.run_id}"
    tags = {
        "git_sha": sha,
        "dataset_version": dsv,
        "run_type": experiment,
        "trace_id": trace_id,
        "tracking_mode": _server_status()["mode"],
    }
    if extra_tags:
        tags.update({str(k): str(v) for k, v in extra_tags.items()})
    handle.set_tags(tags)
    if params:
        handle.log_params(params)
    if metrics:
        handle.log_metrics(metrics)
    snap = handle.end()
    record = snap.as_dict()
    record["start_time"] = int(time.time() * 1000)
    record["source"] = _server_status()["mode"]
    _append_local_run(record)
    return record


# -- routes ---------------------------------------------------------------
@router.get("/status")
def status() -> dict[str, Any]:
    """Tracking-backend status + per-experiment run counts (§18.4)."""
    st = _server_status()
    local = _load_local_runs()
    server = _server_runs(None) if st["mode"] == "server" else []
    runs = server or local
    counts = {name: sum(1 for r in runs if r.get("experiment") == name) for name in EXPERIMENTS}
    st["run_counts"] = counts
    st["total_runs"] = len(runs)
    st["git_sha"] = _git_sha()
    return st


@router.get("/experiments")
def experiments() -> dict[str, Any]:
    """The three tracked experiments with their param/metric schema (§18.4)."""
    st = _server_status()
    local = _load_local_runs()
    server = _server_runs(None) if st["mode"] == "server" else []
    runs = server or local
    items = []
    for spec in ALL_SPECS:
        exp_runs = [r for r in runs if r.get("experiment") == spec.name]
        items.append(
            {
                **spec.as_dict(),
                "run_count": len(exp_runs),
                "latest_metrics": exp_runs[-1]["metrics"] if exp_runs else {},
            }
        )
    return {"experiments": items, "mode": st["mode"], "metrics_ref": "§15.2"}


@router.get("/runs")
def runs(
    experiment: str | None = Query(default=None, description="Filter by experiment name"),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """List tracked runs (server if connected, else local journal), newest first."""
    if experiment is not None and experiment not in EXPERIMENTS:
        raise HTTPException(status_code=400, detail=f"unknown experiment {experiment!r}")
    st = _server_status()
    server = _server_runs(experiment) if st["mode"] == "server" else []
    if server:
        result = server
    else:
        result = [
            r
            for r in _load_local_runs()
            if experiment is None or r.get("experiment") == experiment
        ]
    result.sort(key=lambda r: int(r.get("start_time", 0)), reverse=True)
    return {"runs": result[:limit], "mode": st["mode"], "count": len(result)}


@router.post("/track/retrieval")
def track_retrieval(
    k: int = Query(default=_DEFAULT_K, ge=1, le=50),
    candidate_limit: int = Query(default=200, ge=10, le=2000),
    role: str = Depends(current_role),
) -> dict[str, Any]:
    """Run a LIVE retrieval eval over the graph and log it to MLflow (§18.4/§18.7).

    Reuses :func:`kg_eval.retrieval_eval.run_retrieval_eval` over the active store
    (Neo4j server profile / Kuzu embedded) — real Recall@k / MRR / Precision@k /
    nDCG on the golden set — no mocks.
    """
    from kg_common import get_settings as _gs
    from kg_eval.retrieval_eval import GOLDEN, run_retrieval_eval

    store = get_store()
    t0 = time.perf_counter()
    report = run_retrieval_eval(store, k=k, candidate_limit=candidate_limit)
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
    agg = report.aggregate.as_dict()
    metrics = {
        "recall_at_k": float(agg["recall_at_k"]),
        "precision_at_k": float(agg["precision_at_k"]),
        "hit_at_k": float(agg["hit_at_k"]),
        "mrr": float(agg["mrr"]),
        "ndcg_at_k": float(agg["ndcg_at_k"]),
        "average_precision": float(agg["average_precision"]),
        "n_queries": float(len(report.per_query)),
        "latency_ms": latency_ms,
    }
    params = {
        "retriever": "keyword-overlap",
        "embedding_model": _gs().embedding_model,
        "k": k,
        "candidate_limit": candidate_limit,
        "golden_size": len(GOLDEN),
        "rerank": False,
    }
    return _track(RETRIEVAL_EXPERIMENT, params, metrics, store=store)


def _scalar(store: Any, cypher: str) -> float:
    """Run a single-value aggregate query, tolerating store quirks (→ 0.0)."""
    try:
        rows = store.rows(cypher)
        if rows and rows[0] and rows[0][0] is not None:
            return float(rows[0][0])
    except Exception:
        pass
    return 0.0


@router.post("/track/extraction")
def track_extraction(role: str = Depends(current_role)) -> dict[str, Any]:
    """Log graph-derived extraction-quality metrics to MLflow (§18.4, §8.3).

    Реальные метрики поверх ЖИВОГО графа: evidence-coverage измерений (доля
    Measurement-узлов, связанных с Evidence — §8.3 «no source span → no graph
    fact»), средняя confidence и счётчики сущностей/связей/evidence. Запросы —
    store-agnostic (property-фильтры по STRING ``label``/``type``), работают и на
    Neo4j (server), и на Kuzu (embedded).
    """
    store = get_store()
    counts = store.counts()
    try:
        by_label = store.counts_by_label()
    except Exception:
        by_label = {}

    total_rels = int(counts.get("rels", 0))
    measurements = int(by_label.get("Measurement", 0))
    avg_conf = _scalar(
        store, "MATCH ()-[r:Rel]->() WHERE r.confidence IS NOT NULL RETURN avg(r.confidence)"
    )
    supported_edges = _scalar(
        store, "MATCH ()-[r:Rel]->() WHERE r.type = 'SUPPORTED_BY' RETURN count(r)"
    )
    linked_measurements = _scalar(
        store,
        "MATCH (m:Node)-[:Rel]-(e:Node) "
        "WHERE m.label = 'Measurement' AND e.label = 'Evidence' "
        "RETURN count(DISTINCT m)",
    )
    coverage = (linked_measurements / measurements) if measurements else 0.0

    metrics = {
        "entity_count": float(counts.get("nodes", 0)),
        "relation_count": float(total_rels),
        "evidence_count": float(by_label.get("Evidence", 0)),
        "measurement_count": float(measurements),
        "avg_confidence": round(avg_conf, 4),
        "evidence_coverage": round(coverage, 4),
        "supported_by_edges": supported_edges,
        "measurements_without_evidence": float(max(0.0, measurements - linked_measurements)),
    }
    params = {
        "source": "live-graph",
        "runtime_profile": get_settings().runtime_profile,
        "labels_tracked": len(by_label),
    }
    return _track(EXTRACTION_EXPERIMENT, params, metrics, store=store)


class TrackRequest(BaseModel):
    """Generic run-ingest payload for external evaluators (§18.4)."""

    experiment: str = Field(description="one of: extraction | retrieval | answer")
    params: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    tags: dict[str, str] = Field(default_factory=dict)


@router.post("/track")
def track(req: TrackRequest = Body(...), role: str = Depends(current_role)) -> dict[str, Any]:
    """Ingest an externally-computed run (e.g. ``kg-eval run``, agent answer-run).

    The generic path for the ``answer`` experiment and any offline evaluator: it
    logs the supplied params/metrics to MLflow with the same provenance tags.
    """
    store = get_store()
    return _track(req.experiment, req.params, req.metrics, store=store, extra_tags=req.tags)


@router.get("/experiments/catalog")
def experiments_catalog() -> dict[str, Any]:
    """Static catalogue of experiment names (extraction/retrieval/answer)."""
    return {
        "extraction": EXTRACTION_EXPERIMENT,
        "retrieval": RETRIEVAL_EXPERIMENT,
        "answer": ANSWER_EXPERIMENT,
    }

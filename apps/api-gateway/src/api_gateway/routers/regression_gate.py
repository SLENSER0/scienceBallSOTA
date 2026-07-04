"""Eval regression-gate + Markdown/HTML report with run-to-run diff (§18.11).

CI-ворота качества над ЖИВЫМ графом: прогоняет golden-набор ретрива (§18.6,
``kg_eval.retrieval_eval.run_retrieval_eval``) над активным store (server-профиль
Neo4j / embedded Kuzu), доводит §15.2-метрики живыми измерениями citation-precision
и unsupported-rate (по рёбрам ``SUPPORTED_BY``→Evidence, как в бенчмарке §23.31),
сравнивает результат с (а) baseline-порогами и (б) ПРЕДЫДУЩИМ прогоном из истории,
и возвращает pass/fail-вердикт + exit-code + читаемый отчёт (Markdown + автономный
HTML) со сводкой по категориям §15.1 и diff-колонками. Каждый прогон дописывается в
историю (``<artifacts>/eval/regression/``), отчёты публикуются рядом.

Вся gate/diff/render-логика переиспользована из :mod:`kg_eval.regression_gate` —
роутер только собирает живые метрики, ведёт историю прогонов и отдаёт отчёт.

Эндпоинты:

* ``POST /api/v1/regression-gate/run``   — живой прогон → gate + отчёт (+ запись в историю).
* ``POST /api/v1/regression-gate/check`` — gate над переданными метриками (CI / искусственная
  регрессия из acceptance §18.11), store не трогается.
* ``GET  /api/v1/regression-gate/history`` — сводка прошлых прогонов.
* ``GET  /api/v1/regression-gate/report``  — последний HTML-отчёт (``text/html``).
* ``GET  /api/v1/regression-gate/baseline`` — активные пороги (§15.2).
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from api_gateway.auth import current_role
from api_gateway.deps import get_store
from kg_eval.regression_gate import DEFAULT_SPECS, GateResult, MetricSpec, evaluate_gate

router = APIRouter(prefix="/api/v1/regression-gate", tags=["regression-gate"])

_K = 10
# §15.2 metrics we can measure live over the graph; the gate spec set is the
# subset of the canonical DEFAULT_SPECS restricted to these (thresholds reused).
_LIVE_METRICS = frozenset(
    {
        "recall_at_10",
        "mrr",
        "ndcg_at_10",
        "precision_at_10",
        "citation_precision",
        "unsupported_rate",
    }
)
_LIVE_SPECS: tuple[MetricSpec, ...] = tuple(s for s in DEFAULT_SPECS if s.name in _LIVE_METRICS)


# --- Run history persistence -------------------------------------------------


def _history_dir() -> Path:
    """``<artifacts_dir>/eval/regression`` — created on demand (idempotent)."""
    from kg_common import get_settings

    root = Path(get_settings().artifacts_dir) / "eval" / "regression"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run_files() -> list[Path]:
    """Stored run JSONs, oldest-first (filenames are zero-padded timestamps)."""
    return sorted(_history_dir().glob("run-*.json"))


def _load_run(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _previous_metrics() -> dict[str, float] | None:
    """Metrics of the most recent stored run (the diff baseline), if any."""
    files = _run_files()
    if not files:
        return None
    run = _load_run(files[-1])
    if not run:
        return None
    metrics = run.get("metrics")
    return {k: float(v) for k, v in metrics.items()} if isinstance(metrics, dict) else None


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[5]),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


# --- Live metric collection --------------------------------------------------


def _supported_ids(store: Any, ids: list[str]) -> set[str]:
    """Subset of ``ids`` with a SUPPORTED_BY→Evidence edge (citation support)."""
    if not ids:
        return set()
    try:
        rows = store.rows(
            "MATCH (n:Node)-[:Rel {type:'SUPPORTED_BY'}]->(e:Node {label:'Evidence'}) "
            "WHERE n.id IN $ids RETURN DISTINCT n.id",
            {"ids": ids},
        )
        return {str(r[0]) for r in rows}
    except Exception:
        # Degrade: treat all as supported rather than fabricate unsupported claims.
        return set(ids)


def _collect_live_metrics(store: Any) -> tuple[dict[str, float], int]:
    """Run the golden retrieval eval + citation/unsupported over the live graph.

    Returns ``(metrics, golden_size)`` where ``metrics`` carries the §15.2 keys the
    live gate checks (recall/mrr/ndcg/precision @10 + citation-precision + unsupported).
    """
    from kg_eval.retrieval_eval import GOLDEN, rank_entities, run_retrieval_eval

    report = run_retrieval_eval(store, k=_K)
    agg = report.aggregate.as_dict()

    cites: list[float] = []
    unsup: list[float] = []
    for query, relevant in GOLDEN:
        rel = set(relevant)
        ranked = rank_entities(store, query)
        topk = ranked[:_K]
        supported = _supported_ids(store, topk)
        n_sup = len(supported)
        rel_sup = sum(1 for i in topk if i in supported and i in rel)
        cites.append(rel_sup / n_sup if n_sup else 0.0)
        unsup.append((len(topk) - n_sup) / len(topk) if topk else 0.0)
    n = max(1, len(GOLDEN))

    metrics = {
        "recall_at_10": round(float(agg["recall_at_k"]), 6),
        "mrr": round(float(agg["mrr"]), 6),
        "ndcg_at_10": round(float(agg["ndcg_at_k"]), 6),
        "precision_at_10": round(float(agg["precision_at_k"]), 6),
        "citation_precision": round(sum(cites) / n, 6),
        "unsupported_rate": round(sum(unsup) / n, 6),
    }
    return metrics, len(GOLDEN)


# --- Report publishing -------------------------------------------------------


def _publish_reports(result: GateResult, run_id: str) -> dict[str, str | None]:
    """Write Markdown + HTML report next to the run history; return their paths."""
    out: dict[str, str | None] = {"markdown_path": None, "html_path": None}
    try:
        base = _history_dir()
        md = base / f"report-{run_id}.md"
        html = base / f"report-{run_id}.html"
        md.write_text(result.to_markdown(), encoding="utf-8")
        html.write_text(result.to_html(), encoding="utf-8")
        # Stable "latest" aliases for CI / the report endpoint.
        (base / "report-latest.md").write_text(result.to_markdown(), encoding="utf-8")
        (base / "report-latest.html").write_text(result.to_html(), encoding="utf-8")
        out["markdown_path"] = str(md)
        out["html_path"] = str(html)
    except Exception:
        pass
    return out


def _persist_run(run_id: str, metrics: dict[str, float], result: GateResult, meta: dict) -> None:
    try:
        payload = {
            "run_id": run_id,
            "generated_at": result.generated_at,
            "git_sha": meta.get("git_sha", ""),
            "dataset_version": meta.get("dataset_version", ""),
            "verdict": result.verdict,
            "exit_code": result.exit_code,
            "metrics": metrics,
        }
        (_history_dir() / f"run-{run_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
    except Exception:
        pass


def _result_payload(result: GateResult, extra: dict[str, Any]) -> dict[str, Any]:
    payload = result.as_dict()
    payload["markdown"] = result.to_markdown()
    payload["html"] = result.to_html()
    payload.update(extra)
    return payload


# --- Request models ----------------------------------------------------------


class RunRequest(BaseModel):
    dataset_version: str = Field(default="seed", description="Dataset version tag for provenance")
    write_report: bool = Field(default=True, description="Publish Markdown/HTML report files")


class CheckRequest(BaseModel):
    current: dict[str, float] = Field(..., description="Current-run §15.2 metrics")
    previous: dict[str, float] | None = Field(
        default=None, description="Previous-run metrics to diff against (optional)"
    )
    git_sha: str = Field(default="", description="Provenance: git sha of the current run")
    dataset_version: str = Field(default="", description="Provenance: dataset version")


# --- Endpoints ---------------------------------------------------------------


@router.get("/baseline")
def baseline() -> dict:
    """Active per-metric gate thresholds and directions (§15.2)."""
    return {
        "k": _K,
        "specs": [
            {
                "metric": s.name,
                "label": s.display(),
                "category": s.category,
                "higher_is_better": s.higher_is_better,
                "threshold": s.threshold,
                "tol": s.tol,
                "live": s.name in _LIVE_METRICS,
            }
            for s in DEFAULT_SPECS
        ],
    }


@router.get("/history")
def history(limit: int = 20) -> dict:
    """Summary of past runs (verdict + metrics + provenance), newest-first."""
    runs = []
    for path in reversed(_run_files()):
        run = _load_run(path)
        if run:
            runs.append(run)
        if len(runs) >= max(1, limit):
            break
    return {"count": len(runs), "runs": runs}


@router.post("/run")
def run(req: RunRequest, role: str = Depends(current_role)) -> dict:
    """Live regression-gate run over the graph → verdict + diff report (§18.11).

    Собирает §15.2-метрики живым прогоном golden-набора, сравнивает с baseline и
    предыдущим прогоном, пишет отчёт и историю. ``verdict``=``fail`` / ``exit_code``≠0
    при регрессии или пробитии порога.
    """
    store = get_store()
    t0 = time.perf_counter()
    metrics, golden_size = _collect_live_metrics(store)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    previous = _previous_metrics()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    git_sha = _git_sha()
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")

    result = evaluate_gate(
        metrics,
        previous=previous,
        specs=_LIVE_SPECS,
        git_sha=git_sha,
        dataset_version=req.dataset_version,
        generated_at=generated_at,
    )

    # Persist AFTER computing the diff so `previous` was the prior run, not this one.
    meta = {"git_sha": git_sha, "dataset_version": req.dataset_version}
    _persist_run(run_id, metrics, result, meta)
    report_paths = _publish_reports(result, run_id) if req.write_report else {}

    return _result_payload(
        result,
        {
            "run_id": run_id,
            "git_sha": git_sha,
            "golden_size": golden_size,
            "k": _K,
            "elapsed_ms": elapsed_ms,
            "has_previous": previous is not None,
            "current_metrics": metrics,
            "previous_metrics": previous,
            **report_paths,
        },
    )


@router.post("/check")
def check(req: CheckRequest) -> dict:
    """Gate a provided metrics dict (CI / artificial-degradation acceptance) (§18.11).

    Не трогает граф: сверяет ``current`` с baseline-порогами и (если задан)
    ``previous`` прогоном. Служит для CI-интеграции и проверки acceptance «gate
    фейлит при искусственном ухудшении метрики».
    """
    if not req.current:
        raise HTTPException(status_code=400, detail="current metrics required")
    result = evaluate_gate(
        req.current,
        previous=req.previous,
        git_sha=req.git_sha,
        dataset_version=req.dataset_version,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    return _result_payload(result, {"has_previous": req.previous is not None})


@router.get("/report", response_class=HTMLResponse)
def report() -> HTMLResponse:
    """Latest published HTML report (``text/html``); 404 if no run yet (§18.11)."""
    path = _history_dir() / "report-latest.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no report yet — run the gate first")
    return HTMLResponse(content=path.read_text(encoding="utf-8"))

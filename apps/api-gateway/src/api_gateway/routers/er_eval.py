"""Golden-set ER quality F1 + regression-gate API (§8.12).

Exposes the labelled golden entity-resolution evaluation (``kg_er.eval``) over
HTTP so the demo can show a concrete quality number ("Material F1 = 1.00,
Person F1 = 0.91") and a live PASS/FAIL of the CI regression gate. The resolver
is run over the golden mention sets on the deterministic scoring path, so the
result is reproducible and does not depend on the live graph.

Endpoints (all read-only, no curator role required):

* ``GET /api/v1/er/eval``            — full report: pairwise/B³/purity metrics
  and threshold PASS/FAIL for every entity type, plus the aggregate gate.
* ``GET /api/v1/er/eval/thresholds`` — the per-type F1 acceptance thresholds
  that CI defends (from ``kg_er/data/er_eval_thresholds.yaml``).

This is the read/observe side of §8.12; the enforcing side is the pytest gate
``packages/kg_er/tests/test_golden_eval.py`` run in CI.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/er/eval", tags=["er-eval"])


# --------------------------------------------------------------------------- #
# Schemas                                                                      #
# --------------------------------------------------------------------------- #
class PRFModel(BaseModel):
    precision: float
    recall: float
    f1: float


class TypeEvalModel(BaseModel):
    entity_type: str
    file: str
    threshold: float
    f1: float
    passed: bool
    n_mentions: int
    n_gold_clusters: int
    n_predicted_clusters: int
    backend: str
    pairwise: PRFModel
    b_cubed: PRFModel
    purity: float
    inverse_purity: float


class EvalReportModel(BaseModel):
    passed: bool
    min_f1: float
    mean_f1: float
    n_types: int
    types: list[TypeEvalModel]


class ThresholdsModel(BaseModel):
    thresholds: dict[str, float]


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #
def _to_type_model(d: dict[str, Any]) -> TypeEvalModel:
    m = d["metrics"]
    return TypeEvalModel(
        entity_type=d["entity_type"],
        file=d["file"],
        threshold=d["threshold"],
        f1=d["f1"],
        passed=d["passed"],
        n_mentions=d["n_mentions"],
        n_gold_clusters=d["n_gold_clusters"],
        n_predicted_clusters=m["n_predicted_clusters"],
        backend=d["backend"],
        pairwise=PRFModel(**m["pairwise"]),
        b_cubed=PRFModel(**m["b_cubed"]),
        purity=m["purity"],
        inverse_purity=m["inverse_purity"],
    )


@router.get("", response_model=EvalReportModel)
def er_eval() -> EvalReportModel:
    """Run the golden ER evaluation and return per-type F1 + the gate verdict."""
    try:
        from kg_er.eval import evaluate_all  # lazy: pulls rapidfuzz/pandas
    except Exception as exc:  # pragma: no cover - import/env failure
        raise HTTPException(status_code=503, detail=f"kg_er unavailable: {exc}") from exc

    try:
        report = evaluate_all().as_dict()
    except Exception as exc:  # pragma: no cover - eval must not 500 the screen
        raise HTTPException(status_code=500, detail=f"ER eval failed: {exc}") from exc

    return EvalReportModel(
        passed=report["passed"],
        min_f1=report["min_f1"],
        mean_f1=report["mean_f1"],
        n_types=report["n_types"],
        types=[_to_type_model(t) for t in report["types"]],
    )


@router.get("/thresholds", response_model=ThresholdsModel)
def er_eval_thresholds() -> ThresholdsModel:
    """Per-type pairwise-F1 acceptance thresholds enforced by the CI gate (§8.12)."""
    try:
        from kg_er.eval import load_thresholds
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=503, detail=f"kg_er unavailable: {exc}") from exc
    return ThresholdsModel(thresholds=load_thresholds())

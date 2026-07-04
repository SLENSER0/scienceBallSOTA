"""§13.25 Живое табло качества — golden + deterministic answer-quality metrics.

«Мы измеряем собственную точность». Прогоняет ЖИВОГО агента (server-профиль
Neo4j :8000) по golden-набору (§15.1, :func:`kg_eval.golden.load_cases`) и
считает пять заголовочных метрик answer-quality из §15.2 ДЕТЕРМИНИРОВАННО, без
LLM-судьи, переиспользуя готовые модули :mod:`kg_eval`:

* **citation precision** — :func:`kg_eval.citation_check.check_citations`:
  доля процитированных ``evidence_id``, которые резолвятся в реальный Evidence-узел
  графа (phantom-цитата = провал, §18.10);
* **unsupported-claim rate** — :func:`kg_eval.claim_support.label_claims`:
  доля claim'ов без разрешимой ссылки ИЛИ с числом, которого нет в
  процитированном evidence;
* **numeric accuracy** — та же разметка: доля *числовых* claim'ов, все числа
  которых подтверждены evidence (guardrail §16 «no numeric claim without
  evidence»);
* **unit accuracy** — :func:`kg_eval.unit_accuracy.unit_accuracy`: доля единиц
  ответа, совместимых по физической размерности с ожидаемыми (``expected_constraint_units``);
* **contradiction-detection recall** — доля golden-кейсов с ``expect_contradiction``,
  где агент вернул непустой ``contradictions`` payload.

Роутер НЕ содержит собственной числовой логики — только сборка входов из живого
:class:`~kg_common.dto.AnswerPayload` и резолв цитат против графа (как
:mod:`api_gateway.routers.rag_checks`). Агрегат опционально пишется в MLflow-эксперимент
``answer`` с зафиксированным «no-LLM deterministic» judge в тегах (воспроизводимость, §15.3).

* ``GET  /api/v1/quality-board/info``  — каталог метрик, пороги §15.2, размер golden.
* ``POST /api/v1/quality-board/run``   — golden → живой агент → табло метрик + per-case разбивка.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api_gateway.auth import current_role
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/quality-board", tags=["quality-board"])

# Пороги §15.2 для gate табло (higher-is-better, кроме unsupported_claim_rate).
THRESHOLDS: dict[str, float] = {
    "citation_precision": 0.90,
    "unsupported_claim_rate": 0.10,  # ниже — лучше
    "numeric_accuracy": 0.90,
    "unit_accuracy": 0.90,
    "contradiction_recall": 0.80,
}
# Метрики, для которых меньшее значение лучше (единственная — доля unsupported).
LOWER_IS_BETTER: frozenset[str] = frozenset({"unsupported_claim_rate"})

JUDGE = "deterministic-no-llm (kg_eval §18.10)"


# --- graph helpers ---------------------------------------------------------


def _existing_evidence_ids(store: Any, ids: list[str]) -> set[str]:
    """Subset of ``ids`` that resolve to a real Evidence node (§7.4).

    A cited id absent here is a **phantom citation** → citation-precision penalty
    (§18.10). Degrades to the input set on query error rather than fabricating
    phantoms out of a transient DB failure.
    """
    if not ids:
        return set()
    try:
        rows = store.rows(
            "MATCH (e:Node) WHERE e.id IN $ids "
            "AND (e.label='Evidence' OR e.type='Evidence') RETURN DISTINCT e.id",
            {"ids": ids},
        )
        found = {str(r[0]) for r in rows}
        return found or set(ids)
    except Exception:
        return set(ids)


def _run_agent(query: str, role: str, use_llm: bool, geography: str | None) -> Any:
    from agent_service.agent import answer_query

    geo = geography if geography and geography != "all" else None
    return answer_query(query, get_store(), role=role, use_llm=use_llm, geography=geo)


# --- per-answer metric extraction ------------------------------------------


def _collect_citations(answer: Any) -> tuple[list[str], dict[str, str]]:
    """Cited evidence ids + an ``id/marker → text`` evidence map (§18.10).

    Keys both the raw ``evidence_id`` and the inline marker digits (``[1]`` →
    ``1``) so :func:`kg_eval.claim_support.label_claims` resolves whichever the
    answer markdown actually cites.
    """
    cited_ids: list[str] = []
    evidence: dict[str, str] = {}
    for cit in getattr(answer, "citations", []) or []:
        ref = getattr(cit, "evidence", None)
        if ref is None:
            continue
        text = str(getattr(ref, "text", None) or "")
        eid = str(getattr(ref, "evidence_id", "") or "")
        marker = str(getattr(cit, "marker", "") or "").strip("[]").strip()
        if eid:
            cited_ids.append(eid)
            evidence[eid] = text
        if marker:
            evidence[marker] = text
    return cited_ids, evidence


def _answer_units(answer_markdown: str) -> list[str]:
    """Distinct unit tokens attached to numbers in the answer (§18.8)."""
    from kg_eval.numeric_check import extract_numbers

    seen: list[str] = []
    for _value, unit in extract_numbers(answer_markdown):
        if unit and unit not in seen:
            seen.append(unit)
    return seen


def _unit_pairs(expected_units: list[str], actual_units: list[str]) -> list[tuple[str, str | None]]:
    """Pair each expected unit with the best actual unit for §18.8 scoring.

    Prefers an actual unit sharing the expected one's physical dimension
    (``mg/L`` ↔ ``g/L``); falls back to the first extracted unit, else ``None``
    (no unit judged — counts against compatible-rate).
    """
    from kg_eval.unit_accuracy import judge_unit

    pairs: list[tuple[str, str | None]] = []
    for exp in expected_units:
        chosen: str | None = None
        for act in actual_units:
            if judge_unit(exp, act).compatible:
                chosen = act
                break
        if chosen is None and actual_units:
            chosen = actual_units[0]
        pairs.append((exp, chosen))
    return pairs


def _score_case(store: Any, case: Any, answer: Any) -> dict[str, Any]:
    """Deterministic per-case metric row (§15.2) — no LLM, fully reproducible."""
    from kg_eval.citation_check import check_citations
    from kg_eval.claim_support import label_claims
    from kg_eval.unit_accuracy import unit_accuracy

    answer_md = str(getattr(answer, "answer_markdown", "") or "")
    cited_ids, evidence = _collect_citations(answer)

    # 1) citation precision — phantom-aware against the live graph (§18.10).
    known = _existing_evidence_ids(store, cited_ids)
    cit = check_citations(cited_ids, sorted(known))

    # 2/3) unsupported-claim rate + numeric grounding — one deterministic pass.
    claim_res = label_claims(answer_md, evidence)
    numeric_claims = [c for c in claim_res.claims if c.numbers]
    numeric_supported = sum(1 for c in numeric_claims if c.supported)
    numeric_n = len(numeric_claims)
    numeric_acc = (numeric_supported / numeric_n) if numeric_n else None
    numeric_unsupported = numeric_n - numeric_supported

    # 4) unit accuracy — expected constraint units vs answer units (§18.8).
    expected_units = list(getattr(case, "expected_constraint_units", []) or [])
    unit_stats: dict[str, Any] | None = None
    if expected_units:
        pairs = _unit_pairs(expected_units, _answer_units(answer_md))
        unit_stats = unit_accuracy(pairs)

    # 5) contradiction-detection recall — only for cases that expect one.
    expect_contra = bool(getattr(case, "expect_contradiction", False))
    contra_found = len(getattr(answer, "contradictions", []) or []) > 0

    return {
        "id": getattr(case, "id", ""),
        "title": getattr(case, "title", ""),
        "query": getattr(case, "query", ""),
        "n_citations": len(cited_ids),
        "citation_precision": round(cit.precision, 4),
        "phantom_citations": list(cit.phantom),
        "n_claims": len(claim_res.claims),
        "unsupported_claim_rate": round(claim_res.unsupported_claim_rate, 4),
        "numeric_claims": numeric_n,
        "numeric_claims_without_evidence": numeric_unsupported,
        "numeric_accuracy": None if numeric_acc is None else round(numeric_acc, 4),
        "expected_units": expected_units,
        "answer_units": _answer_units(answer_md),
        "unit_accuracy": None if unit_stats is None else round(unit_stats["compatible_rate"], 4),
        "expect_contradiction": expect_contra,
        "contradiction_found": contra_found,
        # micro-aggregation numerators/denominators (kept for correct averaging).
        "_cited_total": len(cit.cited),
        "_cited_known": len(cit.cited) - len(cit.phantom),
        "_claims_total": len(claim_res.claims),
        "_claims_unsupported": sum(1 for c in claim_res.claims if not c.supported),
        "_numeric_total": numeric_n,
        "_numeric_supported": numeric_supported,
        "_unit_total": (unit_stats["n"] if unit_stats else 0),
        "_unit_compatible": (
            round(unit_stats["compatible_rate"] * unit_stats["n"]) if unit_stats else 0
        ),
    }


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Micro-average the per-case rows into the headline board (§15.2)."""

    def ratio(num: int, den: int, *, default: float) -> float:
        return round(num / den, 4) if den else default

    cited_total = sum(r["_cited_total"] for r in rows)
    cited_known = sum(r["_cited_known"] for r in rows)
    claims_total = sum(r["_claims_total"] for r in rows)
    claims_unsupported = sum(r["_claims_unsupported"] for r in rows)
    numeric_total = sum(r["_numeric_total"] for r in rows)
    numeric_supported = sum(r["_numeric_supported"] for r in rows)
    numeric_no_ev = numeric_total - numeric_supported
    unit_total = sum(r["_unit_total"] for r in rows)
    unit_compatible = sum(r["_unit_compatible"] for r in rows)

    contra_cases = [r for r in rows if r["expect_contradiction"]]
    contra_hits = sum(1 for r in contra_cases if r["contradiction_found"])

    metrics = {
        "citation_precision": ratio(cited_known, cited_total, default=1.0),
        "unsupported_claim_rate": ratio(claims_unsupported, claims_total, default=0.0),
        "numeric_accuracy": ratio(numeric_supported, numeric_total, default=1.0),
        "unit_accuracy": ratio(unit_compatible, unit_total, default=1.0),
        "contradiction_recall": ratio(contra_hits, len(contra_cases), default=1.0),
    }

    gates = {}
    for name, value in metrics.items():
        thr = THRESHOLDS[name]
        passed = value <= thr if name in LOWER_IS_BETTER else value >= thr
        gates[name] = {"value": value, "threshold": thr, "passed": bool(passed)}

    return {
        "metrics": metrics,
        "gates": gates,
        "passed": all(g["passed"] for g in gates.values()),
        "support": {
            "cited_total": cited_total,
            "cited_known": cited_known,
            "claims_total": claims_total,
            "claims_unsupported": claims_unsupported,
            "numeric_total": numeric_total,
            "numeric_claims_without_evidence": numeric_no_ev,
            "unit_total": unit_total,
            "contradiction_cases": len(contra_cases),
            "contradiction_hits": contra_hits,
        },
        # Phase-5 guardrail (§16): «no numeric claim without evidence».
        "numeric_guardrail_ok": numeric_no_ev == 0,
    }


def _strip_internal(row: dict[str, Any]) -> dict[str, Any]:
    """Drop the ``_`` aggregation helpers before returning a case to the client."""
    return {k: v for k, v in row.items() if not k.startswith("_")}


def _log_mlflow(board: dict[str, Any], *, n: int) -> dict[str, Any] | None:
    """Log the board to the ``answer`` MLflow experiment; pin the judge (§15.3)."""
    try:
        from kg_common.mlflow_utils import start_run
        from kg_eval.mlflow_experiments import ANSWER_EXPERIMENT

        handle = start_run(ANSWER_EXPERIMENT, dataset_version="golden-seed")
        handle.set_tags(
            {
                "eval_suite": "quality-board",
                "judge_model": JUDGE,
                "gate_passed": str(board["passed"]),
            }
        )
        handle.log_params({"suite": "quality-board", "n": n, "judge_model": JUDGE})
        handle.log_metrics({f"qb_{k}": float(v) for k, v in board["metrics"].items()})
        return handle.end().as_dict()
    except Exception:
        return None


# --- request model ---------------------------------------------------------


class RunRequest(BaseModel):
    use_llm: bool = Field(
        default=False,
        description="OSS-LLM синтез (медленнее, реалистичнее) vs детерминированный шаблон",
    )
    role: str = Field(default="researcher", description="Роль, под которой отвечает агент")
    suite: str = Field(default="domain_science_ball", description="Golden-набор (§15.1)")
    log_mlflow: bool = Field(default=True, description="Писать агрегат в MLflow answer-эксперимент")


# --- endpoints -------------------------------------------------------------


@router.get("/info")
def quality_board_info() -> dict[str, Any]:
    """Metric catalogue, §15.2 thresholds, judge and golden size (§13.25)."""
    from kg_eval.golden import load_cases

    try:
        n = len(load_cases("domain_science_ball"))
    except Exception:
        n = 0
    return {
        "judge_model": JUDGE,
        "metrics": [
            {"id": "citation_precision", "label": "Точность цитирования", "lower_is_better": False},
            {"id": "unsupported_claim_rate", "label": "Неподтв. утв.", "lower_is_better": True},
            {"id": "numeric_accuracy", "label": "Точность чисел", "lower_is_better": False},
            {"id": "unit_accuracy", "label": "Точность единиц", "lower_is_better": False},
            {
                "id": "contradiction_recall",
                "label": "Recall противоречий",
                "lower_is_better": False,
            },
        ],
        "thresholds": THRESHOLDS,
        "lower_is_better": sorted(LOWER_IS_BETTER),
        "golden_size": n,
        "note": (
            "Детерминированные проверки без LLM-судьи (§18.10): phantom-цитата = провал; "
            "числовой claim без evidence нарушает guardrail §16 «numeric claim without evidence»."
        ),
    }


@router.post("/run")
def quality_board_run(req: RunRequest, role: str = Depends(current_role)) -> dict[str, Any]:
    """Run the golden set through the live agent → quality board (§13.25).

    Для каждого golden-кейса (§15.1) прогоняет живого агента (Neo4j :8000),
    собирает цитаты/числа/единицы/противоречия из :class:`AnswerPayload` и считает
    пять answer-quality метрик §15.2 детерминированно. Возвращает агрегат с
    порогами-гейтами, per-case разбивку и (опц.) MLflow-run для воспроизводимости.
    """
    from kg_eval.golden import load_cases

    store = get_store()
    try:
        cases = load_cases(req.suite)
    except Exception:
        cases = load_cases("domain_science_ball")

    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            answer = _run_agent(case.query, req.role, req.use_llm, None)
        except Exception as exc:  # a single failing case must not sink the board
            rows.append(
                {
                    "id": getattr(case, "id", ""),
                    "title": getattr(case, "title", ""),
                    "query": getattr(case, "query", ""),
                    "error": str(exc),
                    "_cited_total": 0,
                    "_cited_known": 0,
                    "_claims_total": 0,
                    "_claims_unsupported": 0,
                    "_numeric_total": 0,
                    "_numeric_supported": 0,
                    "_unit_total": 0,
                    "_unit_compatible": 0,
                    "expect_contradiction": bool(getattr(case, "expect_contradiction", False)),
                    "contradiction_found": False,
                }
            )
            continue
        rows.append(_score_case(store, case, answer))

    board = _aggregate(rows)
    board["golden_size"] = len(rows)
    board["judge_model"] = JUDGE
    board["cases"] = [_strip_internal(r) for r in rows]
    board["mlflow_run"] = _log_mlflow(board, n=len(rows)) if req.log_mlflow else None
    return board

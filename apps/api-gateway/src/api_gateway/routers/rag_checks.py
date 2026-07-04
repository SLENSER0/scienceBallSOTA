"""§18.9 RAGAS + DeepEval RAG-checks — faithfulness / hallucination / citation-groundedness.

Прогоняет ЖИВОГО агента (server-профиль Neo4j :8000) и меряет его
evidence-first ответ отраслевыми RAG-метриками: пять RAGAS-метрик
(``faithfulness`` / ``answer_relevancy`` / ``context_precision`` /
``context_recall`` / ``answer_correctness``) и DeepEval-набор
(``FaithfulnessMetric`` / ``AnswerRelevancyMetric`` / ``ContextualPrecisionMetric`` /
``HallucinationMetric`` + кастомная GEval «citation groundedness»). Вся числовая
логика — в :mod:`kg_eval.rag_checks` (детерминированный open-weight-free судья,
§23.33); роутер лишь собирает :class:`~kg_eval.rag_checks.RagSample` из ответа
агента (``answer_markdown`` + процитированные evidence-спаны), резолвит цитаты
против графа (фантом = hard fail, §18.10) и логирует метрики в MLflow-эксперимент
``answer`` c зафиксированным judge-моделью в тегах (воспроизводимость, §18.9).

* ``GET  /api/v1/rag-checks/info``     — каталог метрик, пороги, judge-модель, размер golden.
* ``POST /api/v1/rag-checks/evaluate`` — один живой запрос → полный per-sample отчёт.
* ``POST /api/v1/rag-checks/run``      — golden-набор (§18.6) → агрегат + MLflow-run (suite ragas).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api_gateway.auth import current_role
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/rag-checks", tags=["rag-checks"])


# --- graph helpers ---------------------------------------------------------


def _existing_evidence_ids(store: Any, ids: list[str]) -> set[str]:
    """Subset of ``ids`` that resolve to a real Evidence node (§7.4).

    A cited id absent here is a **phantom citation** downstream. Degrades to the
    input set on query error rather than fabricating phantoms.
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


def _reference_text(store: Any, relevant_ids: tuple[str, ...]) -> str:
    """Ground-truth reference = canonical text/name of the golden's relevant node."""
    for nid in relevant_ids:
        try:
            rows = store.rows(
                "MATCH (n:Node {id:$id}) RETURN coalesce(n.text, n.name, '')",
                {"id": nid},
            )
            if rows and rows[0][0]:
                return str(rows[0][0])
        except Exception:
            continue
    return ""


def _sample_from_answer(store: Any, question: str, ground_truth: str, answer: Any) -> Any:
    """Build a :class:`kg_eval.rag_checks.RagSample` from a live AnswerPayload."""
    from kg_eval.rag_checks import RagSample

    contexts: list[str] = []
    cited_ids: list[str] = []
    evidence: dict[str, str] = {}
    for cit in getattr(answer, "citations", []) or []:
        ref = getattr(cit, "evidence", None)
        if ref is None:
            continue
        text = getattr(ref, "text", None) or ""
        eid = str(getattr(ref, "evidence_id", "") or "")
        marker = str(getattr(cit, "marker", "") or "").strip("[]")
        if text:
            contexts.append(text)
        if eid:
            cited_ids.append(eid)
            evidence[eid] = text
        if marker:
            evidence[marker] = text

    known = _existing_evidence_ids(store, cited_ids)
    return RagSample(
        question=question,
        answer=str(getattr(answer, "answer_markdown", "") or ""),
        contexts=tuple(contexts),
        ground_truth=ground_truth,
        cited_ids=tuple(cited_ids),
        evidence=evidence,
        known_ids=tuple(sorted(known)),
    )


def _run_agent(query: str, role: str, use_llm: bool, geography: str | None) -> Any:
    from agent_service.agent import answer_query

    geo = geography if geography and geography != "all" else None
    return answer_query(query, get_store(), role=role, use_llm=use_llm, geography=geo)


def _log_mlflow(agg: Any, *, suite: str) -> dict[str, Any] | None:
    """Log the aggregate to the ``answer`` MLflow experiment; pin judge in tags (§18.9)."""
    try:
        from kg_common.mlflow_utils import start_run
        from kg_eval.mlflow_experiments import ANSWER_EXPERIMENT

        metrics: dict[str, float] = {f"ragas_{k}": float(v) for k, v in agg.ragas.items()}
        metrics.update({f"deepeval_{k}": float(v) for k, v in agg.deepeval.items()})
        metrics["n_passed"] = float(agg.n_passed)
        metrics["n_phantom"] = float(agg.n_phantom)
        handle = start_run(ANSWER_EXPERIMENT, dataset_version="golden-seed")
        handle.set_tags(
            {
                "eval_suite": f"ragas:{suite}",
                "judge_model": agg.judge_model,
                "gate_passed": str(agg.passed),
            }
        )
        handle.log_params({"suite": suite, "n": agg.n, "judge_model": agg.judge_model})
        handle.log_metrics(metrics)
        return handle.end().as_dict()
    except Exception:
        return None


# --- request models --------------------------------------------------------


class EvaluateRequest(BaseModel):
    query: str
    ground_truth: str = ""
    role: str = "researcher"
    use_llm: bool = True
    geography: str | None = None


class RunRequest(BaseModel):
    use_llm: bool = Field(default=False, description="Use OSS LLM synthesis (slower) vs template")
    log_mlflow: bool = Field(default=True, description="Log aggregate to MLflow answer experiment")


# --- endpoints -------------------------------------------------------------


@router.get("/info")
def rag_checks_info() -> dict[str, Any]:
    """Metric catalogue, thresholds, fixed judge model and golden size (§18.9)."""
    from kg_eval.rag_checks import (
        DEEPEVAL_METRICS,
        DEFAULT_THRESHOLDS,
        HIGHER_IS_WORSE,
        JUDGE_MODEL,
        RAGAS_METRICS,
    )
    from kg_eval.retrieval_eval import GOLDEN

    return {
        "judge_model": JUDGE_MODEL,
        "ragas_metrics": list(RAGAS_METRICS),
        "deepeval_metrics": list(DEEPEVAL_METRICS),
        "thresholds": DEFAULT_THRESHOLDS,
        "higher_is_worse": sorted(HIGHER_IS_WORSE),
        "golden_size": len(GOLDEN),
        "note": (
            "Open-weight-free deterministic judge (no closed o3-mini) — §23.33; "
            "citation groundedness: any phantom citation is a hard fail (§18.10)."
        ),
    }


@router.post("/evaluate")
def rag_checks_evaluate(req: EvaluateRequest, role: str = Depends(current_role)) -> dict[str, Any]:
    """Run one live query through the agent and score its answer (§18.9).

    Returns the full per-sample RAGAS + DeepEval report plus the RAGAS row and
    DeepEval ``LLMTestCase`` mappings that fed the metrics.
    """
    from kg_eval.rag_checks import evaluate_sample, to_deepeval_testcase, to_ragas_format

    store = get_store()
    answer = _run_agent(req.query, req.role, req.use_llm, req.geography)
    sample = _sample_from_answer(store, req.query, req.ground_truth, answer)
    report = evaluate_sample(sample)
    return {
        "report": report.as_dict(),
        "ragas_row": to_ragas_format(sample),
        "deepeval_test_case": to_deepeval_testcase(sample),
        "answer_markdown": sample.answer,
        "n_contexts": len(sample.contexts),
        "n_citations": len(sample.cited_ids),
    }


@router.post("/run")
def rag_checks_run(req: RunRequest, role: str = Depends(current_role)) -> dict[str, Any]:
    """Run the RAGAS suite over the golden set → aggregate + MLflow run (§18.9).

    Прогоняет каждый golden-вопрос (§18.6) через живого агента, берёт текст
    релевантного узла как ground-truth reference, считает RAGAS/DeepEval-метрики
    и агрегирует их с порогами как gate. Метрики пишутся в MLflow-эксперимент
    ``answer`` с зафиксированной judge-моделью в тегах (воспроизводимость).
    """
    from kg_eval.rag_checks import evaluate_batch
    from kg_eval.retrieval_eval import GOLDEN

    store = get_store()
    samples = []
    for query, relevant_ids in GOLDEN:
        gt = _reference_text(store, relevant_ids)
        answer = _run_agent(query, "researcher", req.use_llm, None)
        samples.append(_sample_from_answer(store, query, gt, answer))

    agg = evaluate_batch(samples)
    payload = agg.as_dict()
    payload["golden_size"] = len(samples)
    payload["mlflow_run"] = _log_mlflow(agg, suite="golden") if req.log_mlflow else None
    return payload

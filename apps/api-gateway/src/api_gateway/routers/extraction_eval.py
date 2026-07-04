"""Extraction eval-dashboard endpoint — P/R/F1 + span-IoU + cost/latency (§6.17).

Тонкая обёртка над :mod:`kg_eval.extraction_eval`: прогоняет детерминированный
референс-экстрактор над «золотым» extraction-набором и отдаёт метрики приёмки §6.17
(precision/recall/F1 по типам сущностей, span-accuracy по IoU офсетов, (value, unit)
accuracy для measurements, доля фактов с валидным Evidence, useful-docs rate и
cost/latency на документ) как единый JSON для экрана дашборда.

Расчёт детерминирован, воспроизводим и НЕ зависит от состояния графа (нет LLM, нет
тяжёлых весов) — поэтому эндпойнт безопасен под живой server-профиль и всегда
возвращает одни и те же числа для данной версии ``pipeline_version``.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter

from kg_eval.extraction_eval import (
    IOU_MATCH,
    IOU_STRICT,
    PIPELINE_VERSION,
    load_golden,
    run_eval,
    to_markdown,
)

router = APIRouter(prefix="/api/v1/extraction-eval", tags=["extraction-eval"])


@lru_cache(maxsize=1)
def _report_dict() -> dict:
    """Compute the report once per process (deterministic; cheap regex over golden)."""
    report = run_eval()
    payload = report.as_dict()
    payload["markdown"] = to_markdown(report)
    payload["thresholds"] = {"iou_match": IOU_MATCH, "iou_strict": IOU_STRICT}
    return payload


@router.get("/report")
def extraction_eval_report() -> dict:
    """Full §6.17 extraction-eval report over the golden set (per-type P/R/F1,
    span-IoU, measurement accuracy, evidence coverage, cost/latency per document)."""
    return _report_dict()


@router.get("/golden")
def extraction_eval_golden() -> dict:
    """Catalogue of golden documents with their gold-entity type counts (§6.17)."""
    docs = load_golden()
    out = []
    for doc in docs:
        counts: dict[str, int] = {}
        for ent in doc.entities:
            counts[ent.type] = counts.get(ent.type, 0) + 1
        out.append(
            {
                "doc_id": doc.doc_id,
                "title": doc.title,
                "n_gold": len(doc.entities),
                "by_type": counts,
                "excerpt": doc.text[:180],
            }
        )
    return {"pipeline_version": PIPELINE_VERSION, "n_docs": len(docs), "docs": out}

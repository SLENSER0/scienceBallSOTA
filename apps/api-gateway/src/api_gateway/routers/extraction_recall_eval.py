"""Extraction-recall-by-modality eval endpoint (§25.16).

Тонкая read-only обёртка над :mod:`kg_eval.run_extraction_eval`: прогоняет
детерминированный (без LLM) референс-экстрактор над модально-размеченным «золотым»
набором и отдаёт recall по каждой модальности (``table_row`` / ``catalog_row`` /
``chunk``-prose) и overall, с атрибуцией ``fact → evidence → modality``, отчётом о
«слепых зонах» (blind spots) и сравнением измеренного recall с эвристическими priors
§25.10. Это превращает confidence-of-absence из эвристики в откалиброванное число.

Расчёт детерминирован, воспроизводим и НЕ зависит от состояния графа (нет LLM, нет
тяжёлых весов) — эндпойнт безопасен под живой server-профиль (Neo4j :8000) и всегда
возвращает одни и те же числа для данной версии gold-набора.

New router — wire via ``routers/__init__.py`` (see feature wiring); no edits to
existing modules.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api_gateway.auth import current_role

router = APIRouter(prefix="/api/v1/extraction-recall-eval", tags=["extraction-recall-eval"])


@lru_cache(maxsize=8)
def _report(blind_spot_at: float, backend: str) -> dict[str, Any]:
    """Compute the report once per (threshold, backend) — deterministic over the gold set."""
    from kg_eval.run_extraction_eval import run_extraction_eval, to_markdown

    report = run_extraction_eval(blind_spot_at=blind_spot_at, backend=backend)
    payload = report.as_dict()
    payload["markdown"] = to_markdown(report)
    return payload


@router.get("/config")
def extraction_recall_eval_config() -> dict[str, Any]:
    """Gold-set catalogue: modalities, unit counts and their §25.10 heuristic priors."""
    from kg_eval.run_extraction_eval import load_gold

    units = load_gold()
    by_modality: dict[str, dict[str, int]] = {}
    for u in units:
        row = by_modality.setdefault(u.modality, {"n_units": 0, "n_facts": 0})
        row["n_units"] += 1
        row["n_facts"] += len(u.facts)
    return {
        "n_units": len(units),
        "n_facts": sum(len(u.facts) for u in units),
        "modalities": [
            {"modality": name, **counts} for name, counts in sorted(by_modality.items())
        ],
        "default_blind_spot_at": 0.5,
        "note": (
            "Structured rows parse offline near-perfectly; dense prose needs an LLM, so "
            "its recall is the measured blind spot feeding absence calibration (§25.11)."
        ),
    }


class RunRequest(BaseModel):
    blind_spot_at: float = Field(default=0.5, ge=0.0, le=1.0)
    backend: str = Field(default="offline")


@router.post("/run")
def extraction_recall_eval_run(
    req: RunRequest, role: str = Depends(current_role)
) -> dict[str, Any]:
    """Run the §25.16 extraction-recall eval → per-modality recall, blind spots, attribution.

    Deterministic and read-only: no graph mutation, same gold set → same numbers.
    """
    return _report(round(req.blind_spot_at, 4), req.backend)

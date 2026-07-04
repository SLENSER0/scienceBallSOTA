"""§17.7 unified answer warning-panel endpoint (§5.2.2 «warning panel»).

Одна панель рисков ответа с переходами к деталям: агрегирует **contradictions**,
**low-confidence** результаты, **missing-data** пробелы и **unsupported claims**
(числа без цитат) в единую структуру с цветовой индикацией (``severity``) и
``detail_ref`` на нужный экран UI.

``POST /api/v1/warnings/panel`` — принимает либо ``query`` (тогда прогоняется
живой агент ``answer_query`` на server-профиле Neo4j :8000 и панель строится по
его ответу), либо готовый ``answer`` payload (например, из уже отстримленного
чата — тогда LLM повторно НЕ зовётся). Вся агрегация — в
:mod:`api_gateway.warning_panel` (чистая, детерминированная), которая
переиспользует §13.12 guardrail ``agent_service.answer_validator``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api_gateway import warning_panel as wp
from api_gateway.auth import current_role
from api_gateway.deps import get_store
from kg_common.dto import AnswerPayload

router = APIRouter(prefix="/api/v1/warnings", tags=["warning-panel"])


class WarningPanelRequest(BaseModel):
    # Один из двух источников ответа: живой запрос ИЛИ готовый payload.
    query: str | None = None
    answer: dict[str, Any] | None = None
    role: str = "researcher"
    use_llm: bool = True
    geography: str | None = None  # russia | cis | foreign | global | all | None
    low_confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)


def _resolve_answer(req: WarningPanelRequest) -> AnswerPayload:
    """Взять готовый ``answer`` payload или прогнать живой агент по ``query``."""
    if req.answer is not None:
        try:
            return AnswerPayload.model_validate(req.answer)
        except Exception as exc:  # pydantic ValidationError → 400
            raise HTTPException(400, f"invalid answer payload: {exc}") from exc

    if not req.query or not req.query.strip():
        raise HTTPException(400, "provide either 'query' or a prebuilt 'answer' payload")

    from agent_service.agent import answer_query

    geo = req.geography if req.geography and req.geography != "all" else None
    return answer_query(
        req.query.strip(), get_store(), role=req.role, use_llm=req.use_llm, geography=geo
    )


@router.post("/panel")
def warning_panel(
    req: WarningPanelRequest,
    _role: str = Depends(current_role),
) -> dict[str, Any]:
    """Единая панель предупреждений для одного ответа (§17.7 / §5.2.2).

    Возвращает ``{severity, has_warnings, total, counts, categories[]}``; каждая
    из 4 категорий (contradictions / unsupported_claims / low_confidence /
    missing_data) несёт items с ``detail_ref`` для перехода к деталям.
    """
    answer = _resolve_answer(req)
    panel = wp.build_warning_panel(
        answer, low_confidence_threshold=req.low_confidence_threshold
    )
    return panel.as_dict()

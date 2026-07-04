"""§15.8 Verifier-gate — «блокировка неподкреплённых чисел + scan_gaps как tool».

RU: Реализует последний §7.5-guardrail агентного графа как живой сервис поверх
сервер-профиля (Neo4j :8000). Две связанные гарантии evidence-first:

1. **``scan_gaps`` как tool** (§7.4): по контексту вопроса (материал/свойство/режим →
   резолвинг сущностей → 1-hop scope) тянет открытые ``:Gap``-узлы ``ABOUT`` темы
   **прямо в контекст запроса** — то, что делает node ``gap_analyzer`` перед
   финализацией. Пробелы типа ``missing_source_span`` выделяются отдельно, потому
   что именно они запускают блокирующее правило verifier'а.

2. **Verifier блокирует неподкреплённое число** (§13.16): если в тексте ответа есть
   числовое утверждение без inline-ссылки ``[n]`` (проверка §13.12
   :func:`agent_service.answer_validator.validate_answer`) **и** в контексте запроса
   присутствует сопутствующий пробел ``missing_source_span`` — verifier НЕ
   финализирует ответ (``finalize=false``, ``blocked=true``). Число без источника +
   явно отсутствующий span первоисточника = ответ не может выдаваться за
   проверенный. Если неподкреплённое число есть, но missing_source_span в контексте
   нет — это «warning» (мягкий флаг), финализация проходит.

EN: A post-synthesis gate. Reuses the live Cypher phases from
:mod:`api_gateway.routers.agent_reasoning` (``_resolve`` / ``_graph_query`` /
``_gap_scan`` — all real reads over ``:Node``/``:Rel``) plus the pure §13.12
numeric-claim validator, and folds them into the §15.8 blocking decision. No
rewrite of the agent; no store mutation — read-only.

Endpoints:

* ``POST /api/v1/verifier-gate/scan-gaps`` — body ``{"question": ...}`` → the
  ``scan_gaps`` tool alone: resolved context + gaps pulled into it + the
  ``missing_source_span`` subset + per-type tally + honest tool timing.
* ``POST /api/v1/verifier-gate/verify`` — body ``{"question", "answer",
  "citations"?}`` → runs ``scan_gaps`` over the question context, validates every
  numeric claim in ``answer`` against its inline citations, and returns the §15.8
  gate verdict (``blocked`` / ``finalize`` / ``blockReason`` / ``notes``).
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api_gateway.auth import current_user
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/verifier-gate", tags=["agent"])

# The §11.1 gap type whose presence in the query context arms the blocking rule:
# a numeric claim with no evidence **and** a co-located missing source span (§15.8).
_BLOCKING_GAP_TYPE = "missing_source_span"

# Cap on the id list threaded into the gap-scan IN-clause (keeps Cypher params sane).
_ID_CAP = 40


class ScanBody(BaseModel):
    """POST /scan-gaps payload — вопрос пользователя / the user's question."""

    question: str


class VerifyBody(BaseModel):
    """POST /verify payload — вопрос, черновик ответа и его цитаты.

    ``answer`` — отрендеренный markdown-ответ (текст с inline-маркерами ``[n]``).
    ``citations`` — список приложенных цитат (маркеры/объекты); используется лишь
    для флага «есть ли вообще цитаты» — заземление номеров идёт по маркерам в тексте.
    """

    question: str
    answer: str
    citations: list[Any] = []


def _scan_context(store: Any, question: str) -> dict[str, Any]:
    """Run the ``scan_gaps`` tool live: resolve context → 1-hop scope → gaps ABOUT it.

    This is the ``gap_analyzer``-node behaviour of pulling open gaps straight into the
    query context (§15.8). Reuses the real Cypher phases from
    :mod:`api_gateway.routers.agent_reasoning`; the gap scan itself is wrapped in
    :func:`agent_service.tool_trace.traced_tool` so the step is a genuine, timed tool
    call with graceful-error capture (§13.23) — «scan_gaps как tool».
    """
    from agent_service.tool_trace import traced_tool

    from api_gateway.routers.agent_reasoning import (
        _gap_scan,
        _graph_query,
        _resolve,
        _tokens,
    )

    clock = lambda: time.perf_counter() * 1000.0  # ms clock  # noqa: E731

    tokens = _tokens(question)

    # 1) resolve question → canonical entities; 2) widen scope by 1-hop neighbours.
    resolved = _resolve(store, tokens)
    entity_ids = [e["id"] for e in resolved.get("entities", []) if e.get("id")][:_ID_CAP]
    gq = _graph_query(store, entity_ids)
    related_ids = [n["id"] for n in gq.get("neighbors", []) if n.get("id")]
    scope_ids = list(dict.fromkeys([*entity_ids, *related_ids]))[:_ID_CAP]

    # 3) scan_gaps as a real tool — pulls open Gap nodes ABOUT the scope into context.
    result, entry = traced_tool(
        "scan_gaps", lambda a: _gap_scan(store, a["ids"]), {"ids": scope_ids}, clock
    )
    gaps = (result or {}).get("gaps", [])

    by_type: dict[str, int] = {}
    for g in gaps:
        gt = str(g.get("gapType") or "unknown")
        by_type[gt] = by_type.get(gt, 0) + 1

    # The blocking subset: gaps whose type is missing_source_span (§15.8 trigger).
    missing_source_span = [g for g in gaps if str(g.get("gapType")) == _BLOCKING_GAP_TYPE]

    return {
        "tokens": tokens,
        "entities": resolved.get("entities", []),
        "scopeIds": scope_ids,
        "gaps": gaps,
        "gapCount": len(gaps),
        "byType": by_type,
        "missingSourceSpan": missing_source_span,
        "missingSourceSpanCount": len(missing_source_span),
        "tool": {
            "name": "scan_gaps",
            "status": entry.status,
            "durationMs": round(entry.finished_at - entry.started_at, 1),
            "error": entry.error,
            "resultSize": len(gaps),
        },
    }


def _context_note(scan: dict[str, Any]) -> str:
    """One human line describing what the gap-scan pulled into the query context."""
    n = scan["gapCount"]
    if n == 0:
        return "В контекст запроса не подтянуто ни одного открытого пробела."
    mss = scan["missingSourceSpanCount"]
    parts = [f"В контекст запроса подтянуто открытых пробелов: {n}"]
    if mss:
        parts.append(f"из них без первоисточника (missing_source_span): {mss}")
    return " — ".join(parts) + "."


@router.post("/scan-gaps")
def scan_gaps(body: ScanBody, user: str = Depends(current_user)) -> dict:
    """Run the ``scan_gaps`` tool over a question's context and return the gaps found.

    Resolves the question to canonical entities, widens to a 1-hop scope, and scans
    open ``:Gap`` nodes ``ABOUT`` that scope — folding them straight into the query
    context (§15.8 ``gap_analyzer``). The response carries the resolved ``entities``,
    the ``gaps`` (with a ``byType`` tally), the ``missingSourceSpan`` subset that arms
    the verifier's blocking rule, and the honest ``tool`` timing/status.
    """
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="question is required")
    scan = _scan_context(get_store(), question)
    scan["question"] = question
    scan["contextNote"] = _context_note(scan)
    return scan


@router.post("/verify")
def verify(body: VerifyBody, user: str = Depends(current_user)) -> dict:
    """Apply the §15.8 verifier gate: block a numeric claim that has no evidence when a
    co-located ``missing_source_span`` gap is present in the query context.

    Steps:

    1. run ``scan_gaps`` over the question context (gaps pulled in, ``missing_source_span``
       subset isolated);
    2. validate every numeric claim in ``answer`` against its inline ``[n]`` citations
       (§13.12 :func:`agent_service.answer_validator.validate_answer`);
    3. **block finalization** iff there is at least one numeric claim without evidence
       **and** at least one ``missing_source_span`` gap in the context. Otherwise, an
       unsupported number alone downgrades the verdict to ``warning`` (finalization
       still proceeds), and a fully-grounded answer is ``ok``.

    Returns ``blocked`` / ``finalize`` / ``verdict`` (``blocked``|``warning``|``ok``),
    the human ``blockReason`` and ``notes``, the numeric ``numericValidation`` report,
    and the full ``scan`` context.
    """
    from agent_service.answer_validator import validate_answer

    question = (body.question or "").strip()
    answer = body.answer or ""
    if not question:
        raise HTTPException(status_code=422, detail="question is required")
    if not answer.strip():
        raise HTTPException(status_code=422, detail="answer is required")

    scan = _scan_context(get_store(), question)

    nv = validate_answer(answer, list(body.citations))
    unsupported = nv.numeric_claims_without_evidence
    has_unsupported = bool(unsupported)
    has_missing_span = scan["missingSourceSpanCount"] > 0

    # §15.8 core rule: unsupported number + co-located missing_source_span → block.
    blocked = has_unsupported and has_missing_span

    notes: list[str] = []
    block_reason: str | None = None
    if blocked:
        nums = ", ".join(f"«{u}»" for u in unsupported[:5])
        block_reason = (
            f"Финализация заблокирована: {len(unsupported)} числовое(ых) утверждение(й) "
            f"без ссылки ({nums}) при сопутствующем пробеле missing_source_span "
            f"(нет первоисточника) — {scan['missingSourceSpanCount']} шт. в контексте."
        )
        notes.append(block_reason)
    elif has_unsupported:
        notes.append(
            f"Предупреждение: {len(unsupported)} числовое(ых) утверждение(й) без ссылки, "
            "но сопутствующего missing_source_span в контексте нет — финализация разрешена."
        )
    if has_missing_span and not has_unsupported:
        notes.append(
            f"В контексте есть {scan['missingSourceSpanCount']} пробел(ов) missing_source_span, "
            "но все числа в ответе подкреплены ссылками — блокировки нет."
        )
    if scan["gapCount"] and not has_missing_span:
        notes.append(scan["contextNote"])
    if not notes:
        notes.append("Все числа подкреплены; блокирующих пробелов в контексте нет.")

    verdict = "blocked" if blocked else ("warning" if has_unsupported else "ok")

    return {
        "question": question,
        "answer": answer,
        "blocked": blocked,
        "finalize": not blocked,
        "verdict": verdict,
        "blockReason": block_reason,
        "notes": notes,
        "numericValidation": nv.as_dict(),
        "unsupportedCount": len(unsupported),
        "scan": scan,
        "contextNote": _context_note(scan),
    }

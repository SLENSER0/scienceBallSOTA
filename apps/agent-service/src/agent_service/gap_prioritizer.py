"""Agentic gap prioritizer — карта пробелов с приоритизацией.

The gap-scanner flags *where* knowledge is missing; this decides *what to research first*.
It fans out one prioritization agent per gap (GLM-5.2, concurrent) that scores research
priority 0–100 as impact × feasibility × strategic value, with a rationale and a concrete
next action — so an R&D lead gets a ranked backlog, not a flat list of holes.

OSS models via OpenRouter (§7.5). Agents run concurrently; the count is capped so a
demo run stays bounded (the graph has ~89 gaps).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

from kg_common import get_logger, get_settings

_log = get_logger("gap_prioritizer")
_MAX_WORKERS = 10  # fan out up to 10 scoring agents at once (user-requested)

_GAPS_CYPHER = (
    "MATCH (g:Node {label:'Gap'}) "
    "OPTIONAL MATCH (g)-[:Rel]-(m:Node {label:'Material'}) "
    "RETURN g.id AS id, g.name AS name, g.gap_type AS type, g.domain AS domain, "
    "collect(DISTINCT m.name)[0..2] AS materials LIMIT $lim"
)


@dataclass
class PrioritizedGap:
    id: str
    name: str
    type: str | None
    domain: str | None
    priority: int  # 0..100
    impact: int
    feasibility: int
    rationale: str
    action: str
    scored: bool = True  # False = the model failed to score it (NOT a low priority)
    model: str | None = None
    taxonomy5: str | None = None  # §M12 5-way code (TRUE_GAP / CONTRADICTED / …)
    taxonomy5_ru: str | None = None  # RU label for the badge


_SYSTEM = (
    "Ты — руководитель R&D в горном деле и металлургии. Оцени приоритет закрытия пробела "
    "знаний как сочетание важности (impact), осуществимости (feasibility) и стратегической "
    "ценности. Отвечай СТРОГО по описанию пробела, без выдумок. Верни JSON: "
    '{"priority": 0-100, "impact": 0-100, "feasibility": 0-100, '
    '"rationale": "почему это важно, 1-2 фразы", "action": "конкретный следующий шаг"}.'
)


def _score_once(user: str, model_id: str) -> tuple[dict, str | None]:
    from kg_extractors.llm import get_llm

    llm = get_llm()
    data = llm.complete_json(user, system=_SYSTEM, model=model_id, max_tokens=700)
    return (data if isinstance(data, dict) else {}), (
        llm.used_models[-1] if llm.used_models else None
    )


def _score_gap(g: dict[str, Any]) -> PrioritizedGap:
    """Score one gap; on a silent model failure fall back to the fast model, then mark
    the gap as unscored (adversarial finding: a null-model default of 50/50/50 silently
    sank the high-value «никелевый штейн» to the bottom)."""
    s = get_settings()
    mats = ", ".join(x for x in (g.get("materials") or []) if x) or "н/д"
    user = (
        f"Пробел: {g['name']}\n"
        f"Тип: {g.get('type') or 'н/д'} | Домен: {g.get('domain') or 'н/д'} | Материалы: {mats}\n\n"
        "Оцени приоритет исследования."
    )
    data, model = {}, None
    for model_id in (s.llm_model_synth_quality, s.llm_model_synth):  # quality → fast fallback
        try:
            data, model = _score_once(user, model_id)
            if data.get("priority") is not None:
                break
        except Exception as exc:
            _log.warning(
                "gap_prioritizer.attempt_failed",
                gap=str(g.get("id"))[:60],
                model=model_id,
                error=str(exc)[:100],
            )
    scored = bool(data.get("priority") is not None)
    from kg_retrievers.gap_taxonomy5 import classify_gap_5way

    tax5, tax5_ru = classify_gap_5way(g.get("type"), g.get("absence_confidence"))
    return PrioritizedGap(
        id=str(g.get("id")),
        name=str(g.get("name")),
        type=g.get("type"),
        domain=g.get("domain"),
        priority=int(max(0, min(100, data.get("priority", 0)))) if scored else 0,
        impact=int(max(0, min(100, data.get("impact", 0)))) if scored else 0,
        feasibility=int(max(0, min(100, data.get("feasibility", 0)))) if scored else 0,
        rationale=str(data.get("rationale", "")).strip()
        if scored
        else "не удалось оценить (модель)",
        action=str(data.get("action", "")).strip(),
        scored=scored,
        model=model if scored else None,
        taxonomy5=tax5,
        taxonomy5_ru=tax5_ru,
    )


def _fetch_gaps(store: Any, limit: int) -> list[dict[str, Any]]:
    return [
        {"id": r[0], "name": r[1], "type": r[2], "domain": r[3], "materials": r[4]}
        for r in store.rows(_GAPS_CYPHER, {"lim": max(1, min(limit, 24))})
        if r[0] and r[1]
    ]


def _rank(result: list[PrioritizedGap]) -> dict[str, Any]:
    # Scored gaps ranked by priority; unscored (model failures) kept but pushed to the end
    # and clearly flagged — never mixed into the ranking with a misleading default.
    result.sort(key=lambda g: (g.scored, g.priority), reverse=True)
    return {
        "gaps": [asdict(g) for g in result],
        "count": len(result),
        "usedModels": sorted({m for g in result if (m := g.model)}),
    }


def prioritize_gaps(store: Any, *, limit: int = 12) -> dict[str, Any]:
    """Fan out prioritization agents over the top gaps and return a ranked backlog."""
    gaps = _fetch_gaps(store, limit)
    result: list[PrioritizedGap] = []
    if gaps:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            result = list(pool.map(_score_gap, gaps))
    return _rank(result)


def stream_prioritize_gaps(store: Any, *, limit: int = 12):  # type: ignore[no-untyped-def]
    """Stream each gap the instant its scoring agent finishes (honest done/total progress)."""
    from agent_service.fanout import stream_fanout

    gaps = _fetch_gaps(store, limit)
    scored: list[PrioritizedGap] = []
    for ev, data in stream_fanout(gaps, _score_gap, max_workers=_MAX_WORKERS, label="gap"):
        if ev == "item" and isinstance(data.get("result"), PrioritizedGap):
            g = data["result"]
            scored.append(g)
            yield "gap", {"done": data["done"], "total": data["total"], "gap": asdict(g)}
        elif ev == "start":
            yield "start", data
    ranked = _rank(scored)
    yield "done", {"ranked": [g["id"] for g in ranked["gaps"]], "usedModels": ranked["usedModels"]}

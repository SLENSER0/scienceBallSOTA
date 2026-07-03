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
_MAX_WORKERS = 8

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
    model: str | None = None


_SYSTEM = (
    "Ты — руководитель R&D в горном деле и металлургии. Оцени приоритет закрытия пробела "
    "знаний как сочетание важности (impact), осуществимости (feasibility) и стратегической "
    "ценности. Отвечай СТРОГО по описанию пробела, без выдумок. Верни JSON: "
    '{"priority": 0-100, "impact": 0-100, "feasibility": 0-100, '
    '"rationale": "почему это важно, 1-2 фразы", "action": "конкретный следующий шаг"}.'
)


def _score_gap(g: dict[str, Any]) -> PrioritizedGap:
    from kg_extractors.llm import get_llm

    mats = ", ".join(x for x in (g.get("materials") or []) if x) or "н/д"
    user = (
        f"Пробел: {g['name']}\n"
        f"Тип: {g.get('type') or 'н/д'} | Домен: {g.get('domain') or 'н/д'} | Материалы: {mats}\n\n"
        "Оцени приоритет исследования."
    )
    pri, imp, feas, rationale, action, model = 50, 50, 50, "", "", None
    try:
        llm = get_llm()
        data = llm.complete_json(
            user, system=_SYSTEM, model=get_settings().llm_model_synth_quality, max_tokens=700
        )
        model = llm.used_models[-1] if llm.used_models else None
        if isinstance(data, dict):
            pri = int(max(0, min(100, data.get("priority", 50))))
            imp = int(max(0, min(100, data.get("impact", 50))))
            feas = int(max(0, min(100, data.get("feasibility", 50))))
            rationale = str(data.get("rationale", "")).strip()
            action = str(data.get("action", "")).strip()
    except Exception as exc:
        _log.warning("gap_prioritizer.failed", gap=str(g.get("id"))[:60], error=str(exc)[:120])
        rationale = "оценка недоступна (модель)"

    return PrioritizedGap(
        id=str(g.get("id")),
        name=str(g.get("name")),
        type=g.get("type"),
        domain=g.get("domain"),
        priority=pri,
        impact=imp,
        feasibility=feas,
        rationale=rationale,
        action=action,
        model=model,
    )


def prioritize_gaps(store: Any, *, limit: int = 12) -> dict[str, Any]:
    """Fan out prioritization agents over the top gaps and return a ranked backlog."""
    gaps = [
        {"id": r[0], "name": r[1], "type": r[2], "domain": r[3], "materials": r[4]}
        for r in store.rows(_GAPS_CYPHER, {"lim": max(1, min(limit, 24))})
        if r[0] and r[1]
    ]
    scored: list[PrioritizedGap] = []
    if gaps:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            scored = list(pool.map(_score_gap, gaps))
    scored.sort(key=lambda g: g.priority, reverse=True)
    used = sorted({m for g in scored if (m := g.model)})
    return {
        "gaps": [asdict(g) for g in scored],
        "count": len(scored),
        "usedModels": used,
    }

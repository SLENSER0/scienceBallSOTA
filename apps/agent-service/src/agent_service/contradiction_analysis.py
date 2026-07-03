"""Agentic contradiction arbiter — где литература спорит, и почему.

The gap-scanner flags a Contradiction whenever the graph holds conflicting values for the
same property/material (e.g. Cu-recovery 92% vs 78%). This module turns each such flag
into a *reasoned verdict*: it gathers the conflicting measurements with their provenance
(value, unit, source geography, vintage, evidence text) and asks an arbiter agent
(GLM-5.2) whether it is a GENUINE conflict, or CONTEXT-DEPENDENT (different conditions /
practice / era explain the gap), and which side is better supported.

All OSS models via OpenRouter (§7.5). Leans on the geography/year provenance propagated
onto facts so the agent can reason «отеч. 2016 vs заруб. 2019 → условия различны».
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from kg_common import get_logger, get_settings

_log = get_logger("contradiction")

_LIST_CYPHER = (
    "MATCH (c:Node {label:'Contradiction'}) "
    "OPTIONAL MATCH (c)-[:Rel]-(m:Node {label:'Measurement'}) "
    "OPTIONAL MATCH (c)-[:Rel]-(mat:Node {label:'Material'}) "
    "RETURN c.id AS id, c.name AS name, c.review_status AS status, "
    "collect(DISTINCT m.value_normalized)[0..6] AS vals, "
    "collect(DISTINCT m.normalized_unit)[0..2] AS units, "
    "collect(DISTINCT mat.name)[0..2] AS materials, "
    "count(DISTINCT m) AS ncount "  # aliased so ORDER BY doesn't re-aggregate m (Neo4j)
    "ORDER BY ncount DESC LIMIT $lim"
)

_SIDES_CYPHER = (
    "MATCH (c:Node {id:$cid})-[:Rel]-(m:Node {label:'Measurement'}) "
    "OPTIONAL MATCH (m)-[:Rel]-(e:Node {label:'Evidence'}) "
    "RETURN m.id AS mid, m.value_normalized AS val, m.normalized_unit AS unit, "
    "m.property_name AS prop, m.practice_type AS practice, m.source_year AS year, "
    "m.country AS country, e.text AS text "
    "LIMIT 12"
)


@dataclass
class ContradictionSide:
    value: float | None
    unit: str | None
    property: str | None
    practice: str | None
    year: int | None
    country: str | None
    evidence: str | None


@dataclass
class ContradictionAnalysis:
    id: str
    name: str
    verdict: str  # genuine | context_dependent | resolved | insufficient
    explanation: str
    sides: list[ContradictionSide] = field(default_factory=list)
    recommendation: str = ""
    model: str | None = None

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def list_contradictions(store: Any, limit: int = 40) -> list[dict[str, Any]]:
    """List contradictions with the spread of conflicting values (for the UI list)."""
    out: list[dict[str, Any]] = []
    for r in store.rows(_LIST_CYPHER, {"lim": max(1, min(limit, 200))}):
        vals = [v for v in (r[3] or []) if v is not None]
        out.append(
            {
                "id": r[0],
                "name": r[1],
                "status": r[2],
                "values": vals,
                "unit": (r[4] or [None])[0],
                "material": (r[5] or [None])[0],
                "spread": (max(vals) - min(vals)) if len(vals) >= 2 else 0,
            }
        )
    return out


def _load_sides(store: Any, cid: str) -> list[ContradictionSide]:
    seen: set[tuple] = set()
    sides: list[ContradictionSide] = []
    for r in store.rows(_SIDES_CYPHER, {"cid": cid}):
        key = (r[1], r[2], r[4], r[6])  # value, unit, year, country
        if r[1] is None or key in seen:
            continue
        seen.add(key)
        sides.append(
            ContradictionSide(
                value=r[1],
                unit=r[2],
                property=r[3],
                practice=r[4],
                year=r[5],
                country=r[6],
                evidence=(r[7] or "")[:280] or None,
            )
        )
    return sides


_ARBITER_SYSTEM = (
    "Ты — научный арбитр в горном деле и металлургии. Тебе дают конфликтующие значения "
    "одного показателя из разных источников с их контекстом (значение, единица, практика "
    "отеч./заруб., год, страна, цитата). Реши, СТРОГО по данным: это genuine (настоящий "
    "конфликт при одинаковых условиях), context_dependent (различие объяснимо разными "
    "условиями/практикой/эпохой), resolved (одно значение явно надёжнее) или insufficient "
    '(данных мало). Верни JSON: {"verdict": "...", "explanation": "2-3 фразы", '
    '"recommendation": "что делать инженеру"}.'
)


def analyze_contradiction(store: Any, cid: str) -> ContradictionAnalysis:
    """Run the arbiter agent over one contradiction and return a reasoned verdict."""
    rows = store.rows("MATCH (c:Node {id:$cid}) RETURN c.name AS name", {"cid": cid})
    if not rows:
        raise KeyError(cid)
    name = rows[0][0] or cid
    sides = _load_sides(store, cid)

    verdict, explanation, recommendation, model = "insufficient", "", "", None
    if len(sides) >= 2:
        desc = "\n".join(
            f"- {s.value} {s.unit or ''} | {s.property or ''} | "
            f"практика={s.practice or '?'} год={s.year or '?'} страна={s.country or '?'} | "
            f"«{s.evidence or 'нет цитаты'}»"
            for s in sides[:8]
        )
        user = f"Показатель конфликта: {name}\n\nКонфликтующие значения:\n{desc}\n\nВынеси вердикт."
        try:
            from kg_extractors.llm import get_llm

            llm = get_llm()
            data = llm.complete_json(
                user,
                system=_ARBITER_SYSTEM,
                model=get_settings().llm_model_synth_quality,
                max_tokens=900,
            )
            model = llm.used_models[-1] if llm.used_models else None
            if isinstance(data, dict):
                verdict = str(data.get("verdict", "insufficient")).strip() or "insufficient"
                explanation = str(data.get("explanation", "")).strip()
                recommendation = str(data.get("recommendation", "")).strip()
        except Exception as exc:
            _log.warning("contradiction.analyze_failed", cid=cid[:60], error=str(exc)[:120])
            explanation = "агент-арбитр недоступен; показаны исходные значения"
    else:
        explanation = "недостаточно сопоставимых значений для арбитража"

    return ContradictionAnalysis(
        id=cid,
        name=name,
        verdict=verdict,
        explanation=explanation,
        sides=sides,
        recommendation=recommendation,
        model=model,
    )

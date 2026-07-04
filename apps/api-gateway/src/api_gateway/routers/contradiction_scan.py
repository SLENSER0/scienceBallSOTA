"""Систематическое обнаружение противоречий для арбитра (§13.15 / §15.4).

Существующий арбитр (``/api/v1/arbiter``) умеет *рассуждать* только над теми
противоречиями, что УЖЕ материализованы как узлы ``:Contradiction`` в графе. Но
кто-то должен эти узлы породить. Этот роутер закрывает предшествующий шаг —
**систематический скан** живого графа (Neo4j, server-профиль :8000): он проходит
все ``:Measurement``, группирует их по каноническому ключу
``(material, regime, property)`` и внутри каждой группы находит расходящиеся
значения — конфликты, которые пока НЕ выражены узлом ``:Contradiction``.

Найденные конфликты подаются как *first-class вход для агента-арбитра*: у каждого
кандидата стабильный детерминированный ``id`` (``contra:scan:<hash>`` от тройки
ключа), обогащённый провенанс каждой стороны (значение, единица, практика
отеч./заруб., год, страна, цитата) и вердикт эвристики §15.4 (subtype / severity /
сильнейшая сторона). ``POST …/materialize`` фиксирует кандидата как реальный узел
``:Contradiction`` со связями ``HAS_CLAIM``/``CONTRADICTS`` — после чего его без
изменений подхватывают ``/api/v1/arbiter/{cid}/analyze`` и
``/api/v1/arbiter/{cid}/resolve``.

Переиспользует ДВА чистых модуля (ничего не дублируя):
* :func:`agent_service.contradiction_group.group_contradictions` — группировка по
  тройке ключа и отбор бакетов с ≥2 различными значениями;
* :func:`kg_retrievers.contradiction_detector.detect_contradiction` — эвристика
  §15.4 (numeric_divergence / ci_disjoint / effect_direction, severity, сильнейшая
  сторона по силе доказательства).

Systematic contradiction detection that materializes conflicting measurements as
first-class arbiter input (§13.15).
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api_gateway.auth import current_role
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/contradiction-scan", tags=["contradictions"])

# Все measurement'ы с провенансом + обход к материалу / режиму / цитате. Граф хранит
# рёбра как единый ``:Rel {type:...}``, поэтому связи ищем ненаправленным ``-[:Rel]-``
# (как это уже делает agent_service.contradiction_analysis). Каждое m.* поле —
# grouping-ключ агрегации (m.id уникален, поэтому группировка = «по одному узлу»).
_SCAN_CYPHER = (
    "MATCH (m:Node {label:'Measurement'}) "
    "WHERE m.value_normalized IS NOT NULL AND m.property_name IS NOT NULL {extra} "
    "OPTIONAL MATCH (m)-[:Rel]-(mat:Node {label:'Material'}) "
    "OPTIONAL MATCH (m)-[:Rel]-(reg:Node {label:'ProcessingRegime'}) "
    "OPTIONAL MATCH (m)-[:Rel]-(e:Node {label:'Evidence'}) "
    "RETURN m.id AS mid, m.value_normalized AS val, m.normalized_unit AS unit, "
    "m.property_name AS prop, m.practice_type AS practice, m.source_year AS year, "
    "m.country AS country, m.confidence AS conf, m.evidence_strength AS strength, "
    "m.effect_direction AS effect, m.ci_low AS ci_low, m.ci_high AS ci_high, "
    "m.source_id AS source_id, "
    "collect(DISTINCT mat.name)[0] AS material, "
    "collect(DISTINCT reg.name)[0] AS regime, "
    "collect(DISTINCT e.text)[0] AS evidence "
    "LIMIT $lim"
)

_UNSPECIFIED_MAT = "(материал не указан)"
_ANY_REGIME = "(любой режим)"


def _num(v: Any) -> float | None:
    """Best-effort float, else ``None`` (значения графа приходят строками/None)."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _candidate_id(material: str, regime: str, property_: str) -> str:
    """Стабильный детерминированный id кандидата от тройки ключа (§13.15)."""
    digest = hashlib.sha1(f"{material}|{regime}|{property_}".encode()).hexdigest()
    return f"contra:scan:{digest[:16]}"


def _load_measurements(
    store: Any,
    *,
    material: str | None,
    property_: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Прочитать measurement'ы с провенансом + материалом/режимом из живого графа."""
    extra = ""
    params: dict[str, Any] = {"lim": max(50, min(limit, 5000))}
    if property_:
        extra += " AND m.property_name = $property"
        params["property"] = property_
    records: list[dict[str, Any]] = []
    # NB: str.format() would choke on the Cypher map-literals ({label:'…'}) in
    # _SCAN_CYPHER (KeyError). Substitute only our own {extra} token.
    for r in store.rows(_SCAN_CYPHER.replace("{extra}", extra), params):
        val = _num(r[1])
        if val is None:
            continue
        mat = (r[13] or "").strip() or _UNSPECIFIED_MAT
        if material and mat != material:
            continue
        regime = (r[14] or r[4] or "").strip() or _ANY_REGIME
        records.append(
            {
                "mid": r[0],
                "material": mat,
                "regime": regime,
                "property": r[3] or "",
                "value": val,
                "unit": r[2],
                "practice": r[4],
                "year": r[5],
                "country": r[6],
                "confidence": r[7],
                "evidence_strength": r[8],
                "effect_direction": r[9],
                "ci_low": r[10],
                "ci_high": r[11],
                "source_id": r[12] or r[0],
                "evidence": (r[15] or "")[:280] or None,
            }
        )
    return records


def _verdict(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Свести парную эвристику §15.4 по группе в один вердикт для арбитра.

    Прогоняет :func:`detect_contradiction` по всем парам сторон и берёт максимум по
    severity; primary subtype и сильнейшая сторона наследуются от самой сильной пары.
    """
    from kg_retrievers.contradiction_detector import detect_contradiction

    def _as_measurement(r: dict[str, Any]) -> dict[str, Any]:
        # detect_contradiction (§15.4) читает value_normalized / normalized_unit и
        # опциональные evidence_strength / confidence / ci_low / ci_high / effect_direction.
        return {
            "value_normalized": r["value"],
            "normalized_unit": r["unit"],
            "evidence_strength": r["evidence_strength"],
            "confidence": r["confidence"],
            "ci_low": r["ci_low"],
            "ci_high": r["ci_high"],
            "effect_direction": r["effect_direction"],
        }

    best: dict[str, Any] | None = None
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            a, b = records[i], records[j]
            verdict = detect_contradiction(_as_measurement(a), _as_measurement(b))
            if not verdict.is_contradiction:
                continue
            winner = None
            if verdict.likely_correct == "a":
                winner = a
            elif verdict.likely_correct == "b":
                winner = b
            cand = {
                "subtype": verdict.subtype,
                "severity": verdict.severity,
                "likely_correct_id": winner["mid"] if winner else None,
                "reasons": list(verdict.reasons),
            }
            if best is None or cand["severity"] > best["severity"]:
                best = cand
    if best is None:
        # Значения различны (иначе группа бы не прошла), но эвристика §15.4 не сработала —
        # честно помечаем как numeric-расхождение малой силы, чтобы арбитр всё же увидел.
        vals = sorted(r["value"] for r in records)
        spread = vals[-1] - vals[0]
        base = max(abs(vals[-1]), abs(vals[0])) or 1.0
        best = {
            "subtype": "numeric_divergence",
            "severity": round(min(spread / base, 1.0), 4),
            "likely_correct_id": None,
            "reasons": ["расходящиеся значения одного (material, regime, property)"],
        }
    return best


def _side(r: dict[str, Any]) -> dict[str, Any]:
    """Сторона конфликта в форме, совместимой с арбитром (§16.6 candidates)."""
    return {
        "claim_id": r["mid"],
        "value": r["value"],
        "unit": r["unit"],
        "property": r["property"],
        "practice": r["practice"],
        "year": r["year"],
        "country": r["country"],
        "confidence": r["confidence"],
        "evidence": r["evidence"],
        "source_id": r["source_id"],
    }


def _scan(
    store: Any,
    *,
    material: str | None,
    property_: str | None,
    limit: int,
) -> dict[str, dict[str, Any]]:
    """Ядро скана: тройка-ключ → кандидат-противоречие с обеими сторонами.

    Возвращает mapping ``candidate_id → candidate`` (детерминированно), чтобы
    ``GET /{cid}`` и ``POST /{cid}/materialize`` могли переиспользовать один расчёт.
    """
    from agent_service.contradiction_group import group_contradictions

    records = _load_measurements(store, material=material, property_=property_, limit=limit)
    by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for r in records:
        by_key.setdefault((r["material"], r["regime"], r["property"]), []).append(r)

    # Переиспользуем чистую группировку §13.16: какие тройки несут ≥2 РАЗЛИЧНЫХ значения.
    flat = [
        {"material": r["material"], "regime": r["regime"], "property": r["property"],
         "value": r["value"], "source_id": r["source_id"]}
        for r in records
    ]
    groups = group_contradictions(flat)

    out: dict[str, dict[str, Any]] = {}
    for g in groups:
        key = (g.material, g.regime, g.property)
        recs = by_key.get(key, [])
        if len(recs) < 2:
            continue
        verdict = _verdict(recs)
        cid = _candidate_id(*key)
        # Сортируем стороны сильнейшим доказательством вперёд для устойчивого показа.
        winner_id = verdict["likely_correct_id"]
        recs_sorted = sorted(recs, key=lambda r: (r["mid"] != winner_id, r["mid"]))
        out[cid] = {
            "id": cid,
            "material": g.material,
            "regime": g.regime,
            "property": g.property,
            "name": f"{g.material} · {g.property} @ {g.regime}",
            "values": list(g.values),
            "unit": recs[0].get("unit"),
            "spread": g.spread,
            "sides_count": len(recs),
            "source_ids": list(g.source_ids),
            "materialized": False,
            **verdict,
            "sides": [_side(r) for r in recs_sorted],
        }
    return out


@router.get("")
def scan(
    material: str | None = None,
    property: str | None = None,  # API-имя фильтра (свойство графа)
    limit: int = 1500,
    _role: str = Depends(current_role),
) -> dict:
    """Систематически обнаруженные конфликты, готовые для арбитра (§13.15).

    Отсортированы «сильнейший конфликт сверху» (severity ↓, затем spread ↓).
    Флаг ``materialized`` показывает, есть ли уже узел ``:Contradiction`` в графе.
    """
    store = get_store()
    cands = list(_scan(store, material=material, property_=property, limit=limit).values())
    # Отметить уже материализованные кандидаты (узел с тем же детерминированным id).
    for c in cands:
        node = store.get_node(c["id"])
        c["materialized"] = node is not None and node.get("label") == "Contradiction"
    cands.sort(key=lambda c: (-c["severity"], -c["spread"], c["material"]))
    return {
        "count": len(cands),
        "materialized": sum(1 for c in cands if c["materialized"]),
        "contradictions": cands,
    }


@router.get("/{cid:path}")
def detail(cid: str, _role: str = Depends(current_role)) -> dict:
    """Полный кандидат с обеими сторонами (провенанс) для панели арбитра."""
    store = get_store()
    cands = _scan(store, material=None, property_=None, limit=5000)
    cand = cands.get(cid)
    if cand is None:
        raise HTTPException(status_code=404, detail="scan candidate not found")
    node = store.get_node(cid)
    cand["materialized"] = node is not None and node.get("label") == "Contradiction"
    return cand


class MaterializeBody(BaseModel):
    """Опции материализации (сейчас без параметров — тело для будущих расширений)."""

    note: str = ""


@router.post("/{cid:path}/materialize")
def materialize(
    cid: str,
    body: MaterializeBody | None = None,
    _role: str = Depends(current_role),
) -> dict:
    """Зафиксировать кандидата как first-class узел ``:Contradiction`` для арбитра.

    Создаёт (MERGE, идемпотентно) узел ``:Contradiction`` с тем же детерминированным
    ``id``, связывает его рёбрами ``HAS_CLAIM`` с каждой стороной-``Measurement`` и
    ставит ребро ``CONTRADICTS`` между сильнейшей и остальными сторонами. После этого
    узел без изменений подхватывают ``/api/v1/arbiter/{cid}/analyze`` (рассуждение) и
    ``/api/v1/arbiter/{cid}/resolve`` (человеческое разрешение).
    """
    store = get_store()
    cand = _scan(store, material=None, property_=None, limit=5000).get(cid)
    if cand is None:
        raise HTTPException(status_code=404, detail="scan candidate not found")

    sides = cand["sides"]
    claim_ids = [s["claim_id"] for s in sides]
    if len(claim_ids) < 2:
        raise HTTPException(status_code=422, detail="candidate has fewer than two sides")

    store.upsert_node(
        cid,
        "Contradiction",
        name=cand["name"],
        review_status="open",
        detected_by="systematic_scan",
        subtype=cand["subtype"],
        severity=cand["severity"],
        material=cand["material"],
        regime=cand["regime"],
        property_name=cand["property"],
        value_spread=cand["spread"],
    )
    for mid in claim_ids:
        store.upsert_edge(cid, mid, "HAS_CLAIM", detected_by="systematic_scan")

    # CONTRADICTS: сильнейшая сторона (если известна) против прочих, иначе — цепочкой.
    winner = cand.get("likely_correct_id") or claim_ids[0]
    contradicts = 0
    for mid in claim_ids:
        if mid == winner:
            continue
        store.upsert_edge(
            winner, mid, "CONTRADICTS",
            contradicted=True, detected_by="systematic_scan", subtype=cand["subtype"],
        )
        contradicts += 1

    return {
        "id": cid,
        "materialized": True,
        "claim_ids": claim_ids,
        "contradicts_edges": contradicts,
        "winner_claim_id": winner,
        "arbiter_analyze_url": f"/api/v1/arbiter/{cid}/analyze",
    }

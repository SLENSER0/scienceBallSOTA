"""Числовые range-фасеты по параметрам режимов — гистограммы + слайдеры (§4.7).

Учёный фильтрует эксперименты по диапазону температуры/времени. В графе эти
величины лежат НЕ как свойства узла, а как отдельные ``Parameter``-узлы, которые
``ProcessingRegime`` держит через ребро ``HAS_PARAMETER`` (см.
``kg_extractors.processing_extractor`` — «ProcessingRegime→HAS_PARAMETER→Parameter»):

    (rg:ProcessingRegime)-[:HAS_PARAMETER]->(p:Parameter {name, value_normalized})

где ``name`` ∈ {``temperature_c``, ``duration``, ``pressure``, ``current_density``,
``ph``}. Температура извлекается парсером в °C, длительность (``duration``) — в
часах (``time_h`` доменно). Этот роутер строит распределения ровно этих двух
величин по всему корпусу и отдаёт их фронту в форме гистограмм, поверх которых
рисуются двуручьевые слайдеры.

Эндпоинт делает то, что делает настоящий faceted-поиск (§4.7 aggregations):

* **гистограммы** ``temperature_c`` / ``time_h`` — робастный домен (2-й…98-й
  перцентиль, чтобы единичные выбросы 3000 °C не «сплющивали» бины), значения вне
  домена честно суммируются в крайние бины, так что сумма бинов = общему числу
  точек;
* **cross-filter** — операция-фасет и выбранные диапазоны слайдеров пересчитывают
  и бины (флаг ``selected``/``selectedCount``), и список подходящих режимов;
* **matched** — режимы, у которых есть параметр в выбранном диапазоне температуры
  И времени, с покрытием корпусом (число упоминающих чанков ``MENTIONS``).

Чистое чтение из живого графа (server-профиль, Neo4j). Значения тянутся одним
запросом, гистограммы/перцентили считаются в Python (корпус-масштаб — сотни
точек), поэтому тот же код обслуживает и in-process fake в тестах.
"""

from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, Query

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/range-facets", tags=["range-facets"])

# Parameter.name ключи в графе → (поле фасета, подпись, единица).
_TEMPERATURE = "temperature_c"
_DURATION = "duration"  # хранится как Parameter.name='duration'; доменно = time_h

_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    # (field_key, parameter_name, human label, unit)
    ("temperature_c", _TEMPERATURE, "Температура", "°C"),
    ("time_h", _DURATION, "Длительность", "ч"),
)

# Одно чтение: все температурные/длительностные параметры + их режим.
_PARAMS_CYPHER = (
    "MATCH (rg:Node {label:'ProcessingRegime'})-[:Rel {type:'HAS_PARAMETER'}]->"
    "(p:Node {label:'Parameter'}) "
    "WHERE p.name IN ['temperature_c','duration'] AND p.value_normalized IS NOT NULL "
    "RETURN rg.id AS rid, "
    "coalesce(rg.operation, rg.name, rg.canonical_name, rg.id) AS op, "
    "coalesce(rg.name, rg.canonical_name, rg.id) AS rname, rg.domain AS domain, "
    "p.name AS pname, p.value_normalized AS val"
)

# Покрытие корпусом: сколько чанков упоминает каждый подходящий режим.
# Ребро направлено (Chunk)-[:MENTIONS]->(ProcessingRegime).
_MENTIONS_CYPHER = (
    "MATCH (c:Node {label:'Chunk'})-[:Rel {type:'MENTIONS'}]->"
    "(rg:Node {label:'ProcessingRegime'}) "
    "WHERE rg.id IN $ids "
    "RETURN rg.id AS rid, count(DISTINCT c) AS chunks"
)


def _percentile(sorted_vals: list[float], q: float) -> float:
    """Линейно-интерполированный перцентиль ``q``∈[0,1] по отсортированному списку."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_vals[lo]
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _round(v: float) -> float:
    """Компактное округление под UI (крупные величины — целые, малые — 3 знака)."""
    if v == 0:
        return 0.0
    av = abs(v)
    if av >= 100:
        return round(v)
    if av >= 1:
        return round(v, 1)
    return round(v, 3)


def _build_histogram(
    values: list[float],
    *,
    bins: int,
    robust: bool,
    sel_min: float | None,
    sel_max: float | None,
) -> dict[str, Any]:
    """Гистограмма распределения ``values`` с робастным доменом и cross-фильтром.

    Домен по умолчанию — [p2, p98] (``robust``), чтобы одиночные выбросы не
    сплющивали бины; значения вне домена суммируются в крайние бины (клэмп), так
    что ∑bins = len(values). ``sel_min``/``sel_max`` — положения ручек слайдера:
    по ним считается ``selectedCount`` и помечаются попавшие бины.
    """
    n = len(values)
    if n == 0:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "domainMin": None,
            "domainMax": None,
            "selectedMin": sel_min,
            "selectedMax": sel_max,
            "selectedCount": 0,
            "bins": [],
        }

    ordered = sorted(values)
    raw_min, raw_max = ordered[0], ordered[-1]

    if robust and n >= 8:
        dom_lo = _percentile(ordered, 0.02)
        dom_hi = _percentile(ordered, 0.98)
    else:
        dom_lo, dom_hi = raw_min, raw_max
    if dom_hi <= dom_lo:  # degenerate (all equal / robust collapsed the range)
        dom_lo, dom_hi = raw_min, raw_max
    if dom_hi <= dom_lo:  # still degenerate — pad a symmetric unit window
        pad = abs(dom_lo) * 0.05 or 0.5
        dom_lo, dom_hi = dom_lo - pad, dom_hi + pad

    width = (dom_hi - dom_lo) / bins
    edges = [dom_lo + i * width for i in range(bins + 1)]
    edges[-1] = dom_hi  # kill float drift on the last edge
    counts = [0] * bins

    def _bin_index(v: float) -> int:
        if v <= dom_lo:
            return 0
        if v >= dom_hi:
            return bins - 1
        idx = int((v - dom_lo) / width)
        return min(max(idx, 0), bins - 1)  # clamp float edge cases

    for v in ordered:
        counts[_bin_index(v)] += 1

    # Ползунки: по умолчанию открыты на весь домен.
    lo_sel = sel_min if sel_min is not None else dom_lo
    hi_sel = sel_max if sel_max is not None else dom_hi
    selected_count = sum(1 for v in ordered if lo_sel <= v <= hi_sel)

    bin_dicts: list[dict[str, Any]] = []
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        bin_dicts.append(
            {
                "lo": _round(lo),
                "hi": _round(hi),
                "count": counts[i],
                # бин помечен выбранным, если пересекается с окном слайдера
                "selected": hi >= lo_sel and lo <= hi_sel,
            }
        )

    return {
        "count": n,
        "min": _round(raw_min),
        "max": _round(raw_max),
        "domainMin": _round(dom_lo),
        "domainMax": _round(dom_hi),
        "selectedMin": _round(lo_sel),
        "selectedMax": _round(hi_sel),
        "selectedCount": selected_count,
        "bins": bin_dicts,
    }


def _in_range(vals: list[float], lo: float | None, hi: float | None) -> bool:
    """Есть ли хотя бы одно значение в [lo, hi] (границы None = не ограничено)."""
    return any((lo is None or v >= lo) and (hi is None or v <= hi) for v in vals)


@router.get("/histogram")
def histogram(
    bins: int = Query(default=16, ge=4, le=60),
    robust: bool = Query(default=True),
    operation: str | None = Query(default=None),
    temp_min: float | None = Query(default=None),
    temp_max: float | None = Query(default=None),
    time_min: float | None = Query(default=None),
    time_max: float | None = Query(default=None),
    match_limit: int = Query(default=60, ge=1, le=300),
) -> dict:
    """Гистограммы temperature_c / time_h + список подходящих режимов (§4.7).

    ``operation`` сужает оба распределения и список до режимов этой операции.
    ``temp_*`` / ``time_*`` — положения ручек слайдеров: по ним помечаются бины,
    считается ``selectedCount`` и отбираются режимы, у которых есть параметр в
    обоих выбранных диапазонах одновременно.
    """
    store = get_store()
    rows = store.rows(_PARAMS_CYPHER)

    # Свернуть параметры по режимам: {rid: {op,name,domain, temperature_c:[], time_h:[]}}.
    name_to_field = {_TEMPERATURE: "temperature_c", _DURATION: "time_h"}
    regimes: dict[str, dict[str, Any]] = {}
    op_counts: dict[str, int] = {}

    for rid, op, rname, domain, pname, val in rows:
        field = name_to_field.get(str(pname))
        if field is None or val is None:
            continue
        try:
            fval = float(val)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(fval):
            continue
        op_key = str(op) if op is not None else str(rid)
        rec = regimes.get(rid)
        if rec is None:
            rec = {
                "id": rid,
                "operation": op_key,
                "name": str(rname) if rname is not None else op_key,
                "domain": domain,
                "temperature_c": [],
                "time_h": [],
            }
            regimes[rid] = rec
        rec[field].append(fval)
        op_counts[op_key] = op_counts.get(op_key, 0) + 1

    # Операция-фасет (источник выпадающего списка) — по всему корпусу, до сужения.
    operations = [
        {"operation": k, "count": v}
        for k, v in sorted(op_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    # Сужение по операции (регистронезависимо) для гистограмм и списка.
    op_filter = operation.strip().lower() if operation and operation.strip() else None
    active_regimes = [
        r
        for r in regimes.values()
        if op_filter is None or str(r["operation"]).lower() == op_filter
    ]

    temp_values = [v for r in active_regimes for v in r["temperature_c"]]
    time_values = [v for r in active_regimes for v in r["time_h"]]

    fields_out: dict[str, Any] = {}
    for field_key, _pname, label, unit in _FIELDS:
        vals = temp_values if field_key == "temperature_c" else time_values
        sel_lo = temp_min if field_key == "temperature_c" else time_min
        sel_hi = temp_max if field_key == "temperature_c" else time_max
        hist = _build_histogram(
            vals, bins=bins, robust=robust, sel_min=sel_lo, sel_max=sel_hi
        )
        hist["field"] = field_key
        hist["label"] = label
        hist["unit"] = unit
        fields_out[field_key] = hist

    # Cross-filter: режимы с параметром в обоих выбранных диапазонах.
    temp_active = temp_min is not None or temp_max is not None
    time_active = time_min is not None or time_max is not None
    matched: list[dict[str, Any]] = []
    for r in active_regimes:
        temps, times = r["temperature_c"], r["time_h"]
        if temp_active and not _in_range(temps, temp_min, temp_max):
            continue
        if time_active and not _in_range(times, time_min, time_max):
            continue
        matched.append(
            {
                "id": r["id"],
                "operation": r["operation"],
                "name": r["name"],
                "domain": r["domain"],
                "tempCount": len(temps),
                "tempMin": _round(min(temps)) if temps else None,
                "tempMax": _round(max(temps)) if temps else None,
                "timeCount": len(times),
                "timeMin": _round(min(times)) if times else None,
                "timeMax": _round(max(times)) if times else None,
                "paramCount": len(temps) + len(times),
                "chunks": 0,
            }
        )

    matched.sort(key=lambda m: (-m["paramCount"], m["operation"]))
    matched_total = len(matched)
    matched = matched[:match_limit]

    # Покрытие корпусом (число упоминающих чанков) — одним запросом по matched.
    if matched:
        ids = [m["id"] for m in matched]
        try:
            for rid, chunks in store.rows(_MENTIONS_CYPHER, {"ids": ids}):
                for m in matched:
                    if m["id"] == rid:
                        m["chunks"] = int(chunks or 0)
                        break
        except Exception:  # покрытие опционально — не роняем фасеты
            pass

    return {
        "fields": fields_out,
        "operations": operations,
        "matched": {"count": matched_total, "regimes": matched},
        "filters": {
            "operation": operation,
            "temp_min": temp_min,
            "temp_max": temp_max,
            "time_min": time_min,
            "time_max": time_max,
            "bins": bins,
            "robust": robust,
        },
        "totalRegimes": len(regimes),
    }

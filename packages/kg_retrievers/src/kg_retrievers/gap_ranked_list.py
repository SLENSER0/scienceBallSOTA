"""Gap dashboard — ranked gap list with per-type styling (§5.2.7 / §17.14).

The *gap dashboard* (панель пробелов) surfaces the knowledge gaps of a graph as a
single **ranked list**: one row per gap, sorted best-signal-first, each decorated
with a small per-type *style* (icon + colour + Russian label) so the UI can render
a consistent, scannable legend.

A gap's *type* is one of the canonical :class:`~kg_schema.enums.GapType` values. The
``missing_*`` family (missing property value, baseline, unit, …) denotes an expected
datum that is simply **absent** — rendered *hollow* (outline only) to read as "a
hole"; every other type (unverified claim, contradiction, orphan, …) is a *present*
signal and renders solid.

This is a pure, read-only *builder*: it takes a plain ``list[dict]`` of scored gaps
and returns a frozen :class:`GapRankedList`. No graph access, fully deterministic.

Ranking (§5.2.7): rows sort by **descending score**, ties broken by ``gap_id``
ascending, then ``rank`` is assigned ``1..N`` in that final order. The legend lists
only the distinct types actually present in the (post-filter) rows.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_schema.enums import GapType

# --- Per-type styling (§5.2.7) -------------------------------------------------
# One entry per GapType value. ``hollow`` is True iff the type is a ``missing_*``
# absence gap (rendered outline-only). ``iconKey`` / ``colorToken`` are UI design
# tokens; ``label_ru`` is the Russian display label (RU/EN house style).
GAP_TYPE_STYLE: dict[str, dict] = {
    GapType.MISSING_PROPERTY_VALUE.value: {
        "iconKey": "value",
        "colorToken": "gap.missing",
        "hollow": True,
        "label_ru": "Нет значения свойства",
    },
    GapType.MISSING_BASELINE.value: {
        "iconKey": "baseline",
        "colorToken": "gap.missing",
        "hollow": True,
        "label_ru": "Нет базовой линии",
    },
    GapType.MISSING_PROCESSING_PARAMETER.value: {
        "iconKey": "process",
        "colorToken": "gap.missing",
        "hollow": True,
        "label_ru": "Нет параметра обработки",
    },
    GapType.MISSING_EQUIPMENT.value: {
        "iconKey": "equipment",
        "colorToken": "gap.missing",
        "hollow": True,
        "label_ru": "Нет оборудования",
    },
    GapType.MISSING_UNIT.value: {
        "iconKey": "unit",
        "colorToken": "gap.missing",
        "hollow": True,
        "label_ru": "Нет единицы измерения",
    },
    GapType.MISSING_SOURCE_SPAN.value: {
        "iconKey": "source",
        "colorToken": "gap.missing",
        "hollow": True,
        "label_ru": "Нет источника",
    },
    GapType.UNVERIFIED_CLAIM.value: {
        "iconKey": "unverified",
        "colorToken": "gap.warning",
        "hollow": False,
        "label_ru": "Непроверенное утверждение",
    },
    GapType.CONTRADICTORY_MEASUREMENTS.value: {
        "iconKey": "conflict",
        "colorToken": "gap.danger",
        "hollow": False,
        "label_ru": "Противоречивые измерения",
    },
    GapType.LOW_COVERAGE_MATERIAL.value: {
        "iconKey": "coverage",
        "colorToken": "gap.warning",
        "hollow": False,
        "label_ru": "Низкое покрытие материала",
    },
    GapType.LOW_CONFIDENCE_ENTITY_RESOLUTION.value: {
        "iconKey": "resolution",
        "colorToken": "gap.warning",
        "hollow": False,
        "label_ru": "Низкая уверенность сопоставления",
    },
    GapType.ORPHAN_ENTITY.value: {
        "iconKey": "orphan",
        "colorToken": "gap.info",
        "hollow": False,
        "label_ru": "Изолированная сущность",
    },
    GapType.MISSING_GEOGRAPHY.value: {
        "iconKey": "geography",
        "colorToken": "gap.missing",
        "hollow": True,
        "label_ru": "Нет географии",
    },
    GapType.MISSING_APPLICABILITY_CONDITION.value: {
        "iconKey": "applicability",
        "colorToken": "gap.missing",
        "hollow": True,
        "label_ru": "Нет условия применимости",
    },
    GapType.MISSING_TECHNOECONOMIC.value: {
        "iconKey": "technoeconomic",
        "colorToken": "gap.missing",
        "hollow": True,
        "label_ru": "Нет технико-экономических данных",
    },
    GapType.ONLY_FOREIGN_SOURCES.value: {
        "iconKey": "foreign",
        "colorToken": "gap.warning",
        "hollow": False,
        "label_ru": "Только зарубежные источники",
    },
    GapType.NO_PILOT_DATA.value: {
        "iconKey": "pilot",
        "colorToken": "gap.warning",
        "hollow": False,
        "label_ru": "Нет пилотных данных",
    },
}

# House-style invariants (§5.2.7): every GapType has a style, and hollow tracks the
# ``missing_*`` absence family exactly. Verified at import time.
assert set(GAP_TYPE_STYLE) == {g.value for g in GapType}, "GAP_TYPE_STYLE must cover every GapType"
for _t, _s in GAP_TYPE_STYLE.items():
    assert _s["hollow"] == _t.startswith("missing_"), f"hollow mismatch for {_t}"


@dataclass(frozen=True)
class GapRankedList:
    """Ranked gap list for the dashboard (§5.2.7).

    :param rows: one dict per gap, sorted best-first, each carrying a ``rank``,
        ``score`` and per-type ``style``.
    :param type_legend: the distinct types present in ``rows`` with their styles.
    :param total: number of rows (post-filter).
    """

    rows: tuple[dict, ...]
    type_legend: tuple[dict, ...]
    total: int

    def as_dict(self) -> dict:
        """JSON-serialisable payload (§5.2.7)."""
        return {
            "rows": [dict(r) for r in self.rows],
            "typeLegend": [dict(t) for t in self.type_legend],
            "total": self.total,
        }


def build_gap_ranked_list(
    gaps: list[dict],
    type_filter: set[str] | None = None,
) -> GapRankedList:
    """Build the §5.2.7 ranked gap list from scored gaps.

    Each input gap dict is expected to carry ``gap_id``, ``type`` (a
    :class:`~kg_schema.enums.GapType` value), ``severity`` and ``score``.

    :param gaps: scored gap dicts.
    :param type_filter: if given, keep only gaps whose ``type`` is in the set.
    :returns: a frozen :class:`GapRankedList` with ranks assigned ``1..N``.
    """
    kept = [g for g in gaps if type_filter is None or g.get("type") in type_filter]

    # Sort: descending score, ties broken by gap_id ascending (§5.2.7).
    ordered = sorted(kept, key=lambda g: (-float(g.get("score", 0.0)), str(g.get("gap_id", ""))))

    rows: list[dict] = []
    for rank, g in enumerate(ordered, start=1):
        gtype = g.get("type")
        rows.append(
            {
                "gap_id": g.get("gap_id"),
                "type": gtype,
                "severity": g.get("severity"),
                "rank": rank,
                "score": float(g.get("score", 0.0)),
                "style": GAP_TYPE_STYLE[gtype],
            }
        )

    # Legend: distinct types present in rows, in first-appearance (rank) order.
    seen: dict[str, dict] = {}
    for r in rows:
        gtype = r["type"]
        if gtype not in seen:
            seen[gtype] = {"type": gtype, "style": GAP_TYPE_STYLE[gtype]}
    type_legend = tuple(seen.values())

    return GapRankedList(rows=tuple(rows), type_legend=type_legend, total=len(rows))

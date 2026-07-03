"""Techno-economic indicator extraction over a KuzuGraphStore (§24.22).

Извлечение технико-экономических показателей одного технологического решения.

For a single ``TechnologySolution`` node this reads the ``TechnoEconomicIndicator``
nodes linked to it via ``HAS_TECHNOECONOMIC_INDICATOR`` and exposes each as a frozen
``EconomicIndicator`` — ``{kind, value, unit, note}`` — where ``kind`` is one of the
recognised techno-economic kinds (capex / opex / npv / payback).

Kuzu note: custom node props (e.g. ``note``) are not queryable columns, so the walk
``RETURN``\\ s only the base ``id`` column and every field is read back through
``store.get_node`` (which merges the ``props`` JSON catch-all). The module is
read-only: it never writes to the graph.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_retrievers.graph_store import KuzuGraphStore

# Node label of a techno-economic indicator measurement (§24.22).
INDICATOR_LABEL = "TechnoEconomicIndicator"

# Relation linking a solution to its techno-economic indicators.
INDICATOR_REL = "HAS_TECHNOECONOMIC_INDICATOR"

# Recognised indicator kinds (§24.22): capex/opex/npv/payback.
# capex=капзатраты, opex=операц. затраты, npv=ЧДД, payback=срок окупаемости.
KNOWN_KINDS: frozenset[str] = frozenset({"capex", "opex", "npv", "payback"})

# ``property_name`` -> kind normalisation (срок окупаемости -> payback).
_KIND_ALIASES: dict[str, str] = {"payback_period": "payback"}


@dataclass(frozen=True)
class EconomicIndicator:
    """One techno-economic indicator of a solution (§24.22).

    ``kind`` is one of :data:`KNOWN_KINDS`; ``value``/``unit`` are the normalised
    magnitude and unit; ``note`` is an optional free-text remark (примечание).
    """

    kind: str  # capex / opex / npv / payback
    value: float | None
    unit: str | None
    note: str | None

    def as_dict(self) -> dict:
        """JSON shape ``{kind, value, unit, note}``."""
        return {
            "kind": self.kind,
            "value": self.value,
            "unit": self.unit,
            "note": self.note,
        }


def _normalise_kind(prop: object) -> str | None:
    """Map a node ``property_name`` to a recognised kind, else ``None``."""
    if not isinstance(prop, str) or not prop:
        return None
    kind = _KIND_ALIASES.get(prop, prop)
    return kind if kind in KNOWN_KINDS else None


def _to_indicator(node: dict[str, object]) -> EconomicIndicator | None:
    """Build an :class:`EconomicIndicator` from a get_node dict (``None`` if not TE)."""
    kind = _normalise_kind(node.get("property_name"))
    if kind is None:
        return None
    raw_val = node.get("value_normalized")
    value = float(raw_val) if isinstance(raw_val, (int, float)) else None
    unit = node.get("normalized_unit")
    note = node.get("note")
    return EconomicIndicator(
        kind=kind,
        value=value,
        unit=unit if isinstance(unit, str) else None,
        note=note if isinstance(note, str) else None,
    )


def indicators_for(store: KuzuGraphStore, solution_id: str) -> list[EconomicIndicator]:
    """Techno-economic indicators linked to ``solution_id`` (§24.22).

    Walks ``solution -[HAS_TECHNOECONOMIC_INDICATOR]-> TechnoEconomicIndicator``,
    reads each indicator node via ``get_node`` and returns the recognised
    capex/opex/npv/payback indicators (ordered by indicator node id). An unknown
    solution — or one with no indicators — yields ``[]`` (graceful, no error).
    """
    rows = store.rows(
        "MATCH (s:Node {id:$sid})-[r:Rel]->(ind:Node) "
        "WHERE r.type=$rel AND ind.label=$label "
        "RETURN ind.id ORDER BY ind.id",
        {"sid": solution_id, "rel": INDICATOR_REL, "label": INDICATOR_LABEL},
    )
    out: list[EconomicIndicator] = []
    for row in rows:
        node = store.get_node(row[0])
        if not node:
            continue
        indicator = _to_indicator(node)
        if indicator is not None:
            out.append(indicator)
    return out

"""Applicability-condition extraction and matching (§24.14).

Условия применимости — a ``TechnologySolution`` is only valid inside a stated
operating envelope: pH range, temperature ceiling, feed concentration, throughput,
etc. Each envelope constraint is stored as an ``ApplicabilityCondition`` node linked
to the solution by ``HAS_APPLICABILITY_CONDITION``.

This module reads those conditions off the graph and tests a numeric *context*
(a real-world operating point, e.g. ``{"tds_g_l": 5.0}``) against them so callers
can decide whether a solution applies to a concrete situation.

Kuzu note: an ``ApplicabilityCondition``'s ``parameter`` / ``operator`` / ``value`` /
``note`` are custom node properties, not queryable ``Node`` columns — the query only
matches on base columns (``id`` / ``label``) and every custom field is read back
through :meth:`KuzuGraphStore.get_node`. The module is read-only: it never writes.
"""

from __future__ import annotations

import operator as _operator
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from kg_retrievers.graph_store import KuzuGraphStore

# Node label of the solution an applicability condition constrains (§24.2 / §24.14).
SOLUTION_LABEL = "TechnologySolution"

# Node label of an applicability-condition node (условие применимости).
CONDITION_LABEL = "ApplicabilityCondition"

# Relation linking a solution to each of its applicability conditions.
APPLICABILITY_REL = "HAS_APPLICABILITY_CONDITION"

# Accepted operator spellings -> the two-argument numeric comparator they mean.
# Symbolic (``>=``) and word forms (``gte``) both resolve, so extractor output in
# either convention matches without normalisation elsewhere.
_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    ">=": _operator.ge,
    "ge": _operator.ge,
    "gte": _operator.ge,
    "<=": _operator.le,
    "le": _operator.le,
    "lte": _operator.le,
    ">": _operator.gt,
    "gt": _operator.gt,
    "<": _operator.lt,
    "lt": _operator.lt,
    "==": _operator.eq,
    "=": _operator.eq,
    "eq": _operator.eq,
    "!=": _operator.ne,
    "ne": _operator.ne,
}


@dataclass(frozen=True)
class ApplicabilityCondition:
    """One applicability constraint of a solution (§24.14).

    ``parameter`` is the context key the constraint reads (e.g. ``tds_g_l``);
    ``operator``/``value`` form the numeric test applied to it; ``unit`` and ``note``
    are descriptive. Any field may be ``None`` when the source did not state it.
    """

    condition_id: str
    parameter: str | None
    operator: str | None
    value: float | None
    unit: str | None
    note: str | None

    def as_dict(self) -> dict[str, Any]:
        """JSON shape ``{condition_id, parameter, operator, value, unit, note}``."""
        return {
            "condition_id": self.condition_id,
            "parameter": self.parameter,
            "operator": self.operator,
            "value": self.value,
            "unit": self.unit,
            "note": self.note,
        }


def _as_str(raw: object) -> str | None:
    """Coerce a node property to a non-empty ``str`` (else ``None``)."""
    if isinstance(raw, str) and raw:
        return raw
    return None


def _as_float(raw: object) -> float | None:
    """Coerce a numeric node property to ``float`` (``bool`` and non-numerics -> ``None``)."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


def _condition_from_node(condition_id: str, node: dict[str, Any]) -> ApplicabilityCondition:
    """Build a frozen condition from a ``get_node`` property dict (custom props included)."""
    return ApplicabilityCondition(
        condition_id=condition_id,
        parameter=_as_str(node.get("parameter")),
        operator=_as_str(node.get("operator")),
        value=_as_float(node.get("value")),
        unit=_as_str(node.get("unit")),
        note=_as_str(node.get("note")),
    )


def applicability_for(store: KuzuGraphStore, solution_id: str) -> list[ApplicabilityCondition]:
    """Applicability conditions attached to one solution (§24.14).

    Walks ``solution -[HAS_APPLICABILITY_CONDITION]-> ApplicabilityCondition`` and
    reads each target's custom props through ``get_node``. Conditions come back in
    ascending ``condition_id`` order (deterministic). A solution with no conditions,
    or an unknown ``solution_id``, yields ``[]`` (graceful, never raises).
    """
    rows = store.rows(
        "MATCH (s:Node {id:$sid})-[r:Rel]->(ac:Node) "
        "WHERE r.type=$rel AND ac.label=$label "
        "RETURN DISTINCT ac.id ORDER BY ac.id",
        {"sid": solution_id, "rel": APPLICABILITY_REL, "label": CONDITION_LABEL},
    )
    conditions: list[ApplicabilityCondition] = []
    for row in rows:
        condition_id = row[0]
        node = store.get_node(condition_id)
        if node is None:
            continue
        conditions.append(_condition_from_node(condition_id, node))
    return conditions


def matches_context(condition: ApplicabilityCondition, context: dict[str, Any]) -> bool:
    """Whether ``context`` satisfies ``condition`` (§24.14).

    ``context`` maps parameter names to numeric operating points. Returns ``True``
    iff the condition names a parameter present in ``context`` with a numeric value,
    a recognised operator and a numeric threshold, and the comparison holds. Anything
    under-specified or non-numeric (missing parameter, unknown operator, ``bool`` or
    string context value) yields ``False`` — a condition that cannot be tested does
    not silently pass.
    """
    if condition.parameter is None or condition.value is None or condition.operator is None:
        return False
    comparator = _OPERATORS.get(condition.operator)
    if comparator is None:
        return False
    if condition.parameter not in context:
        return False
    context_value = context[condition.parameter]
    if isinstance(context_value, bool) or not isinstance(context_value, (int, float)):
        return False
    return bool(comparator(float(context_value), condition.value))

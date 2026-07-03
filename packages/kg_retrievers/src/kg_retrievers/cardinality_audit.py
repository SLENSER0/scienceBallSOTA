"""Functional-cardinality invariants over the graph (§8 / §3.16).

Инварианты кардинальности — validates declared per-``(label, rel_type)`` outgoing
cardinality invariants against a :class:`KuzuGraphStore`. For example, every
``Measurement`` must have exactly one ``OF_PROPERTY`` edge and exactly one
``HAS_UNIT`` edge, and every ``Composition`` must have at least one
``CONTAINS_ELEMENT`` edge. A rule declares an inclusive ``[min, max]`` range on
the number of outgoing edges of a given ``rel_type`` from every node of a given
``label`` (``max=None`` means unbounded).

Both the node ``label`` and the edge ``type`` are base columns on the generic
``Node`` / ``Rel`` tables (see ``graph_store.py``), so counts are read straight
from Cypher aggregation — no per-node ``props`` lookup is needed.

Read-only: this module never writes to the graph. Результат — frozen dataclasses
with ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_retrievers.graph_store import KuzuGraphStore


@dataclass(frozen=True)
class CardinalityRule:
    """One declared outgoing-cardinality invariant (§3.16).

    Every node of ``label`` must have between ``min`` and ``max`` (inclusive)
    outgoing edges of ``rel_type``. ``max=None`` means no upper bound.
    """

    label: str
    rel_type: str
    min: int
    max: int | None

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "rel_type": self.rel_type,
            "min": self.min,
            "max": self.max,
        }


@dataclass(frozen=True)
class CardinalityViolation:
    """A node whose outgoing edge count breaks a :class:`CardinalityRule`."""

    node_id: str
    rule: CardinalityRule
    observed: int

    def as_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "rule": self.rule.as_dict(),
            "observed": self.observed,
        }


@dataclass(frozen=True)
class CardinalityAudit:
    """Outcome of a cardinality audit over the graph (§8 / §3.16)."""

    checked_nodes: int
    violations: tuple[CardinalityViolation, ...]

    @property
    def ok(self) -> bool:
        """True iff no invariant was violated."""
        return not self.violations

    def as_dict(self) -> dict:
        return {
            "checked_nodes": self.checked_nodes,
            "violations": [v.as_dict() for v in self.violations],
            "ok": self.ok,
        }


# Declared invariants enforced by default (§3.16). Measurement: exactly one
# property and exactly one unit; Composition: at least one contained element.
CARDINALITY_RULES: tuple[CardinalityRule, ...] = (
    CardinalityRule(label="Measurement", rel_type="OF_PROPERTY", min=1, max=1),
    CardinalityRule(label="Measurement", rel_type="HAS_UNIT", min=1, max=1),
    CardinalityRule(label="Composition", rel_type="CONTAINS_ELEMENT", min=1, max=None),
)


def audit_cardinality(
    store: KuzuGraphStore,
    *,
    rules: tuple[CardinalityRule, ...] | None = None,
) -> CardinalityAudit:
    """Check declared outgoing-cardinality invariants against ``store`` (§3.16).

    Проверка инвариантов кардинальности. For each rule, counts the outgoing edges
    of ``rule.rel_type`` from every node of ``rule.label`` and flags any node whose
    count falls outside ``[rule.min, rule.max]``. ``checked_nodes`` is the number of
    distinct nodes whose label appears in any rule.
    """
    active = CARDINALITY_RULES if rules is None else rules

    labels = sorted({r.label for r in active})
    checked_nodes = 0
    if labels:
        rows = store.rows(
            "MATCH (n:Node) WHERE n.label IN $labels RETURN count(n)",
            {"labels": labels},
        )
        checked_nodes = int(rows[0][0]) if rows else 0

    violations: list[CardinalityViolation] = []
    for rule in active:
        rows = store.rows(
            "MATCH (n:Node) WHERE n.label = $label "
            "OPTIONAL MATCH (n)-[r:Rel {type:$rtype}]->() "
            "RETURN n.id, count(r)",
            {"label": rule.label, "rtype": rule.rel_type},
        )
        for node_id, count in rows:
            observed = int(count)
            if observed < rule.min or (rule.max is not None and observed > rule.max):
                violations.append(
                    CardinalityViolation(node_id=node_id, rule=rule, observed=observed)
                )

    return CardinalityAudit(checked_nodes=checked_nodes, violations=tuple(violations))

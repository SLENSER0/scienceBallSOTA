"""Observed edge-schema profiler — data-derived schema (§8.2).

Наблюдаемая схема рёбер. Reconstructs the schema *actually* present in a Kuzu
store by counting every distinct concrete ``(from_label, rel_type, to_label)``
triple and comparing each against the *declared* ``EDGE_SCHEMA`` (with the
virtual ``Entity`` super-label expanded). Any concrete triple that no declared
signature admits is flagged as ``undeclared`` — this complements the declared-
only ``kg_schema`` catalog by surfacing the drift between design and data.

The generic ``Rel`` table stores ``type`` as a base column and every node its
``label`` (see ``graph_store.py``), so all three components come straight from
one Cypher aggregation — no per-node ``props`` lookup is needed. Read-only:
this module never writes to the graph.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.relationships import is_valid_edge


@dataclass(frozen=True)
class ObservedTriple:
    """One concrete ``(from_label, rel_type, to_label)`` triple seen in the data.

    - ``count`` — number of ``Rel`` edges matching this exact triple;
    - ``declared`` — True iff a declared ``EDGE_SCHEMA`` signature admits it
      (``Entity`` expanded to ``ENTITY_LABELS``).
    """

    from_label: str
    rel_type: str
    to_label: str
    count: int
    declared: bool

    def as_dict(self) -> dict:
        return {
            "from_label": self.from_label,
            "rel_type": self.rel_type,
            "to_label": self.to_label,
            "count": self.count,
            "declared": self.declared,
        }


@dataclass(frozen=True)
class ObservedSchemaProfile:
    """Data-derived edge schema of a store (§8.2).

    - ``triples`` — every distinct observed triple, sorted by ``count`` desc then
      by ``(from_label, rel_type, to_label)`` asc;
    - ``undeclared`` — the subset of ``triples`` with ``declared`` False (same order);
    - ``distinct_rel_types`` — every relationship type seen in the data.
    """

    triples: tuple[ObservedTriple, ...]
    undeclared: tuple[ObservedTriple, ...]
    distinct_rel_types: frozenset[str]

    @property
    def fully_declared(self) -> bool:
        """True iff no observed triple is undeclared (empty store counts as clean)."""
        return not self.undeclared

    def as_dict(self) -> dict:
        return {
            "triples": [t.as_dict() for t in self.triples],
            "undeclared": [t.as_dict() for t in self.undeclared],
            "distinct_rel_types": sorted(self.distinct_rel_types),
            "fully_declared": self.fully_declared,
        }


def profile_observed_schema(store: KuzuGraphStore) -> ObservedSchemaProfile:
    """Profile the concrete edge schema present in ``store`` (§8.2).

    Counts distinct ``(from_label, rel_type, to_label)`` triples and checks each
    against the declared ``EDGE_SCHEMA`` (``Entity`` expanded). Triples are sorted
    by count desc, then lexicographically by ``(from, rel, to)`` for stability.
    """
    rows = store.rows("MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.label, r.type, b.label")
    counts: dict[tuple[str, str, str], int] = {}
    rel_types: set[str] = set()
    for from_label, rel_type, to_label in rows:
        if from_label is None or rel_type is None or to_label is None:
            continue
        key = (from_label, rel_type, to_label)
        counts[key] = counts.get(key, 0) + 1
        rel_types.add(rel_type)

    triples = tuple(
        ObservedTriple(
            from_label=f,
            rel_type=r,
            to_label=t,
            count=c,
            declared=is_valid_edge(f, r, t),
        )
        for (f, r, t), c in counts.items()
    )
    triples = tuple(sorted(triples, key=lambda x: (-x.count, x.from_label, x.rel_type, x.to_label)))
    undeclared = tuple(t for t in triples if not t.declared)
    return ObservedSchemaProfile(
        triples=triples,
        undeclared=undeclared,
        distinct_rel_types=frozenset(rel_types),
    )

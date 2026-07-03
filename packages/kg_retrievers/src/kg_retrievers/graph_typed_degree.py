"""Typed (per-relationship-type) node degree over a KuzuGraphStore (§8.15).

Breaks each node's degree down by relationship type — a *role fingerprint* that
:mod:`degree_distribution` (which only totals in + out) does not provide. For a
node that is, say, the source of two ``ABOUT_REGIME`` edges and the target of one
``SUPPORTED_BY`` edge, the typed degree records ``out_by_type={'ABOUT_REGIME':2}``
and ``in_by_type={'SUPPORTED_BY':1}`` separately.

Типизированная степень узла: разбивка входящих и исходящих рёбер по типу связи —
«отпечаток роли», который простая суммарная степень не даёт.

Reads the full graph (all labels, not just entities) via the queryable base
columns ``a.id`` / ``r.type`` / ``b.id`` of the ``Rel`` table
(``MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id, r.type, b.id``); custom node
props are not Kuzu columns and are never touched here. An unknown node id yields
empty ``out_by_type`` / ``in_by_type`` and zero totals.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("graph_typed_degree")

_EDGES_Q = "MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id, r.type, b.id"


@dataclass(frozen=True)
class TypedDegree:
    """Per-relationship-type degree of a single node (§8.15).

    - ``out_by_type`` — relationship type → count of outgoing edges of that type;
    - ``in_by_type`` — relationship type → count of incoming edges of that type;
    - ``total_out`` — sum of all outgoing edge counts;
    - ``total_in`` — sum of all incoming edge counts.

    A node with no incident edge has empty ``out_by_type`` / ``in_by_type`` and
    both totals ``0``.
    """

    node_id: str
    out_by_type: dict[str, int]
    in_by_type: dict[str, int]
    total_out: int
    total_in: int

    def as_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "out_by_type": dict(self.out_by_type),
            "in_by_type": dict(self.in_by_type),
            "total_out": self.total_out,
            "total_in": self.total_in,
        }


def _accumulate(store: KuzuGraphStore) -> dict[str, dict[str, dict[str, int]]]:
    """Per-node ``{'out': {type: n}, 'in': {type: n}}`` from the ``Rel`` table (§8.15).

    Every directed edge ``a -[type]-> b`` adds ``+1`` to ``a``'s outgoing bucket
    for ``type`` and ``+1`` to ``b``'s incoming bucket for ``type``.
    """
    acc: dict[str, dict[str, dict[str, int]]] = {}
    for src, rtype, dst in store.rows(_EDGES_Q):
        out_map = acc.setdefault(src, {"out": {}, "in": {}})["out"]
        out_map[rtype] = out_map.get(rtype, 0) + 1
        in_map = acc.setdefault(dst, {"out": {}, "in": {}})["in"]
        in_map[rtype] = in_map.get(rtype, 0) + 1
    return acc


def _build(node_id: str, buckets: dict[str, dict[str, int]] | None) -> TypedDegree:
    """Assemble a :class:`TypedDegree` from a node's out/in bucket maps (§8.15)."""
    out_by_type = dict(buckets["out"]) if buckets else {}
    in_by_type = dict(buckets["in"]) if buckets else {}
    return TypedDegree(
        node_id=node_id,
        out_by_type=out_by_type,
        in_by_type=in_by_type,
        total_out=sum(out_by_type.values()),
        total_in=sum(in_by_type.values()),
    )


def typed_degree(store: KuzuGraphStore, node_id: str) -> TypedDegree:
    """Typed degree of a single ``node_id`` (§8.15).

    Unknown ids yield empty ``out_by_type`` / ``in_by_type`` and zero totals.
    """
    td = _build(node_id, _accumulate(store).get(node_id))
    _log.info(
        "typed_degree.node",
        node_id=node_id,
        total_out=td.total_out,
        total_in=td.total_in,
    )
    return td


def typed_degree_all(store: KuzuGraphStore) -> dict[str, TypedDegree]:
    """Typed degree of every node with at least one incident edge (§8.15).

    Isolated nodes (no incident edge) do not appear; query them individually via
    :func:`typed_degree`, which returns an empty fingerprint for them.
    """
    acc = _accumulate(store)
    result = {node_id: _build(node_id, buckets) for node_id, buckets in acc.items()}
    _log.info("typed_degree.all", n_nodes=len(result))
    return result

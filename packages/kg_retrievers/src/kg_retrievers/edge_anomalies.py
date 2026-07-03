"""Structural edge-anomaly detection over the entity graph (§8.13 graph hygiene).

Аномалии рёбер / edge anomalies — structural data-quality smells that the store's
``MERGE`` dedup does *not* catch, because dedup keys an edge on the ordered pair
plus its ``rel_type``:

- **self-loops** — a relationship whose source and target are the same node
  (``src == dst``); e.g. an entity that ``CONTRADICTS`` itself. Almost always a
  broken extraction or a mis-resolved coreference.
- **parallel edges** — two or more edges of *differing* ``rel_type`` between the
  same ordered node pair (``a -[:MENTIONS]-> b`` and ``a -[:ABOUT]-> b``). Not
  wrong per se, but a smell worth surfacing: the same directed link asserted under
  conflicting relation semantics.

This module reads a :class:`KuzuGraphStore` (never writes) via the single base
query ``MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id, r.type, b.id``.

Kuzu note: custom edge/node props are not queryable columns, so we RETURN only the
base ``id`` / ``type`` columns here; anything else would be read via
``store.get_node``. Grouping over the returned rows is reliable on empty and
disconnected graphs alike.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from kg_retrievers.graph_store import KuzuGraphStore

_ALL_EDGES = "MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id, r.type, b.id"


@dataclass(frozen=True)
class SelfLoop:
    """A relationship whose endpoints are the same node (§8.13).

    ``node_id`` — узел с петлёй / the looping node; ``rel_type`` — тип ребра.
    """

    node_id: str
    rel_type: str

    def as_dict(self) -> dict:
        return {"node_id": self.node_id, "rel_type": self.rel_type}


@dataclass(frozen=True)
class ParallelEdge:
    """Two+ edges of differing type on one ordered node pair (§8.13).

    ``rel_types`` — отсортированные типы параллельных рёбер / the sorted distinct
    relation types asserted between ``src_id`` and ``dst_id``.
    """

    src_id: str
    dst_id: str
    rel_types: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "src_id": self.src_id,
            "dst_id": self.dst_id,
            "rel_types": list(self.rel_types),
        }


@dataclass(frozen=True)
class EdgeAnomalyReport:
    """Summary of structural edge anomalies in a graph (§8.13).

    ``ok`` истинно, когда аномалий нет / true when no anomaly was found.
    """

    self_loops: tuple[SelfLoop, ...]
    parallel_edges: tuple[ParallelEdge, ...]
    total_edges: int

    @property
    def ok(self) -> bool:
        return not self.self_loops and not self.parallel_edges

    def as_dict(self) -> dict:
        return {
            "self_loops": [s.as_dict() for s in self.self_loops],
            "parallel_edges": [p.as_dict() for p in self.parallel_edges],
            "total_edges": self.total_edges,
            "ok": self.ok,
        }


def detect_edge_anomalies(store: KuzuGraphStore) -> EdgeAnomalyReport:
    """Scan every ``Rel`` edge in ``store`` for self-loops and parallel edges (§8.13)."""
    self_loops: list[SelfLoop] = []
    pair_types: dict[tuple[str, str], set[str]] = defaultdict(set)
    total_edges = 0
    for src, rel_type, dst in store.rows(_ALL_EDGES):
        total_edges += 1
        if src == dst:
            self_loops.append(SelfLoop(node_id=src, rel_type=rel_type))
            continue
        pair_types[(src, dst)].add(rel_type)
    parallel_edges = [
        ParallelEdge(src_id=src, dst_id=dst, rel_types=tuple(sorted(types)))
        for (src, dst), types in pair_types.items()
        if len(types) > 1
    ]
    self_loops.sort(key=lambda s: (s.node_id, s.rel_type))
    parallel_edges.sort(key=lambda p: (p.src_id, p.dst_id))
    return EdgeAnomalyReport(
        self_loops=tuple(self_loops),
        parallel_edges=tuple(parallel_edges),
        total_edges=total_edges,
    )

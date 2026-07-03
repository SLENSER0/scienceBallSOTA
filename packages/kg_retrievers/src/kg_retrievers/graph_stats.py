"""Graph statistics over the Kuzu graph store (§8.13).

Read-only structural snapshot of a :class:`KuzuGraphStore`: total node and edge
counts, per-label and per-relationship-type breakdowns, the average node degree
and the directed graph density.

Статистика графа: число узлов и рёбер, разбивки по меткам узлов и типам связей,
средняя степень и плотность графа.

Everything is computed from queryable Kuzu *base* columns (``n.label`` on the
``Node`` table and ``r.type`` on the ``Rel`` table) — never from the JSON
``props`` catch-all, which Kuzu cannot filter or group on — so the stats stay
Cypher-computed and cheap. An empty store yields all-zeros.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("graph_stats")


@dataclass(frozen=True)
class GraphStats:
    """Structural statistics of a graph store (§8.13).

    - ``n_nodes`` — total number of ``Node`` rows;
    - ``n_edges`` — total number of directed ``Rel`` edges;
    - ``by_label`` — node ``label`` → count, ordered most-frequent first;
    - ``by_rel_type`` — edge ``type`` → count, ordered most-frequent first;
    - ``avg_degree`` — mean total (in + out) degree ``2·E / N``; ``0.0`` when the
      store has no nodes;
    - ``density`` — directed edge density ``E / (N·(N − 1))`` in ``[0, 1]``;
      ``0.0`` when the store has fewer than two nodes.
    """

    n_nodes: int
    n_edges: int
    by_label: dict[str, int]
    by_rel_type: dict[str, int]
    avg_degree: float
    density: float

    def as_dict(self) -> dict:
        return {
            "n_nodes": self.n_nodes,
            "n_edges": self.n_edges,
            "by_label": dict(self.by_label),
            "by_rel_type": dict(self.by_rel_type),
            "avg_degree": self.avg_degree,
            "density": self.density,
        }


def _counts_by_rel_type(store: KuzuGraphStore) -> dict[str, int]:
    """Edge ``type`` → count from the base ``r.type`` column, biggest first (§8.13)."""
    rows = store.rows("MATCH ()-[r:Rel]->() RETURN r.type, count(r) ORDER BY count(r) DESC")
    return {r[0]: r[1] for r in rows}


def graph_stats(store: KuzuGraphStore) -> GraphStats:
    """Compute :class:`GraphStats` over ``store`` (§8.13).

    Reads only the queryable base columns (``n.label`` / ``r.type``); custom node
    props are not columns in Kuzu and are read via ``get_node`` elsewhere, not
    here. An empty store gives all zeros (``avg_degree`` and ``density`` both
    ``0.0``).
    """
    counts = store.counts()
    n_nodes = counts["nodes"]
    n_edges = counts["rels"]
    by_label = store.counts_by_label()
    by_rel_type = _counts_by_rel_type(store)
    avg_degree = (2.0 * n_edges / n_nodes) if n_nodes else 0.0
    density = (n_edges / (n_nodes * (n_nodes - 1))) if n_nodes > 1 else 0.0
    stats = GraphStats(
        n_nodes=n_nodes,
        n_edges=n_edges,
        by_label=by_label,
        by_rel_type=by_rel_type,
        avg_degree=avg_degree,
        density=density,
    )
    _log.info(
        "graph.stats",
        n_nodes=n_nodes,
        n_edges=n_edges,
        avg_degree=avg_degree,
        density=density,
    )
    return stats

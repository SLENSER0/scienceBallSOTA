"""PageRank & personalized PageRank over the entity graph (§3.14 / §17).

Центральность по PageRank / PageRank centrality — a directed projection of the
knowledge graph restricted to :data:`ENTITY_LABELS` nodes. We pull every
entity→entity ``Rel`` edge, build an :class:`networkx.DiGraph`, and run the
power-iteration PageRank. The store carries a ``pagerank`` column that nothing
populates; this module is the (read-only) computation that would feed it.

``personalized_pagerank`` biases the random-walk restart distribution toward a
set of seed entities (personalization mass on valid seeds only). Seeds absent
from the projection are ignored; if *no* seed survives, we fall back to a
uniform restart (i.e. plain PageRank).

Kuzu note: custom node props are not queryable columns, so we RETURN only the
base ``id`` columns via ``store.rows`` and never touch ``get_node`` here.
Results are deterministic: sorted by score descending, ties broken by entity id.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.labels import ENTITY_LABELS

_ENTITY_EDGES = (
    "MATCH (a:Node)-[:Rel]->(b:Node) WHERE a.label IN $l AND b.label IN $l RETURN a.id, b.id"
)


@dataclass(frozen=True)
class PageRankScore:
    """One entity's PageRank score (§3.14 / §17).

    ``entity_id`` — id узла-сущности / entity node id; ``score`` — доля
    стационарного распределения / stationary-distribution mass in ``[0, 1]``.
    """

    entity_id: str
    score: float

    def as_dict(self) -> dict:
        return {"entity_id": self.entity_id, "score": self.score}


def _projection(store: KuzuGraphStore) -> nx.DiGraph:
    """Build the directed entity→entity projection graph (§3.14)."""
    graph: nx.DiGraph = nx.DiGraph()
    for src, dst in store.rows(_ENTITY_EDGES, {"l": list(ENTITY_LABELS)}):
        graph.add_edge(src, dst)
    return graph


def _pagerank(
    graph: nx.DiGraph,
    damping: float,
    personalization: dict[str, float] | None,
    max_iter: int = 100,
    tol: float = 1.0e-6,
) -> dict[str, float]:
    """Pure-python power-iteration PageRank (the algorithm networkx uses).

    We keep the ``nx.DiGraph`` projection but iterate here so the module has no
    hard SciPy dependency. Dangling nodes (no out-edges) redistribute their mass
    over the restart vector ``p``; teleport mass ``(1 - damping)`` is spread the
    same way. Scores sum to ``1.0``.
    """
    nodes = list(graph)
    n = len(nodes)
    out_degree = dict(graph.out_degree())
    # restart / teleport distribution p, normalized to sum 1
    if personalization:
        mass = float(sum(personalization.values()))
        p = {node: personalization.get(node, 0.0) / mass for node in nodes}
    else:
        p = dict.fromkeys(nodes, 1.0 / n)
    dangling_nodes = [node for node in nodes if out_degree[node] == 0]

    x = dict(p)
    for _ in range(max_iter):
        x_last = x
        x = dict.fromkeys(nodes, 0.0)
        dangle_sum = damping * sum(x_last[node] for node in dangling_nodes)
        for node in nodes:
            share = damping * x_last[node] / out_degree[node] if out_degree[node] else 0.0
            for nbr in graph.successors(node):
                x[nbr] += share
        for node in nodes:
            x[node] += dangle_sum * p[node] + (1.0 - damping) * p[node]
        err = sum(abs(x[node] - x_last[node]) for node in nodes)
        if err < n * tol:
            break
    return x


def _rank(
    graph: nx.DiGraph,
    top: int,
    damping: float,
    personalization: dict[str, float] | None,
) -> list[PageRankScore]:
    """Run PageRank on ``graph`` and return the deterministic top scores."""
    if graph.number_of_nodes() == 0:
        return []
    scores = _pagerank(graph, damping, personalization)
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [PageRankScore(entity_id=nid, score=float(s)) for nid, s in ranked[:top]]


def pagerank(store: KuzuGraphStore, top: int = 10, damping: float = 0.85) -> list[PageRankScore]:
    """PageRank centrality over the entity projection (§3.14 / §17).

    Returns up to ``top`` entities ranked by score descending (ties by id). An
    empty projection yields ``[]``. Scores sum to ``1.0`` across the whole graph.
    """
    return _rank(_projection(store), top, damping, None)


def personalized_pagerank(
    store: KuzuGraphStore,
    seeds: list[str],
    top: int = 10,
    damping: float = 0.85,
) -> list[PageRankScore]:
    """Personalized PageRank biased toward ``seeds`` (§3.14 / §17).

    Restart mass is spread uniformly over the seeds present in the projection.
    If no seed is present (or ``seeds`` is empty), we fall back to a uniform
    restart — i.e. plain PageRank. Empty projection yields ``[]``.
    """
    graph = _projection(store)
    valid = [s for s in seeds if graph.has_node(s)]
    personalization = dict.fromkeys(valid, 1.0) if valid else None
    return _rank(graph, top, damping, personalization)

"""Confidence-weighted entity graph projection (§3.14 / §12.8).

A weighted sibling of :func:`kg_retrievers.graph_algos.project_entity_graph`.
Where the plain projection collapses the ``:Entity`` subgraph into a bare
undirected NetworkX graph, this module *keeps* edge confidences: parallel edges
between the same pair of entities are summed into a single ``weight`` attribute.

Проекция графа сущностей с весами по достоверности рёбер. On top of the weighted
graph we expose the *weighted degree strength* of an entity — суммарный вес
инцидентных рёбер — the confidence-weighted analogue of degree centrality.

Kuzu note: the undirected pattern ``(a)-[r:Rel]-(b)`` yields each stored
directed edge twice (once per orientation). We keep only the canonical
orientation (``a.id <= b.id``) so each physical edge is counted exactly once;
``r.confidence`` is read as a base column and a null/absent value counts as 0.0.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.labels import ENTITY_LABELS

# Weighted projection query (§3.14): undirected entity–entity edges carrying
# their confidence. Mirrors the plain projection in ``graph_algos`` but returns
# ``r.confidence`` so parallel edges can be summed into a single weight.
_PROJECTION = (
    "MATCH (a:Node)-[r:Rel]-(b:Node) WHERE a.label IN $l AND b.label IN $l "
    "RETURN a.id, b.id, r.confidence"
)


@dataclass(frozen=True)
class WeightedStrength:
    """An entity id paired with its weighted degree strength (§3.14).

    ``strength`` is the sum of the confidence weights on the entity's incident
    edges — суммарный вес инцидентных рёбер — and is non-negative.
    """

    entity_id: str
    strength: float

    def as_dict(self) -> dict:
        return {"entity_id": self.entity_id, "strength": self.strength}


def project_weighted(store: KuzuGraphStore) -> nx.Graph:
    """Project the ``:Entity`` subgraph into a weighted undirected graph (§3.14).

    Each edge carries a ``weight`` attribute equal to the sum of the confidences
    of all parallel edges between the two entities; a null/missing confidence
    contributes 0.0. Self-loops are dropped and isolated entities are omitted,
    matching :func:`kg_retrievers.graph_algos.project_entity_graph`.
    """
    rows = store.rows(_PROJECTION, {"l": list(ENTITY_LABELS)})
    weights: dict[tuple[str, str], float] = {}
    for a, b, conf in rows:
        if a == b or a > b:  # drop self-loops; keep one orientation per edge
            continue
        weights[(a, b)] = weights.get((a, b), 0.0) + (float(conf) if conf is not None else 0.0)
    graph = nx.Graph()
    for (a, b), w in weights.items():
        graph.add_edge(a, b, weight=w)
    return graph


def weighted_degree_strength(store: KuzuGraphStore, top: int = 10) -> list[WeightedStrength]:
    """Top entities by weighted degree strength — вес инцидентных рёбер (§3.14).

    The strength of an entity is the sum of the ``weight`` of its incident
    edges. Results are ranked strength-first, ties broken by id for
    determinism. An empty graph yields ``[]``.
    """
    graph = project_weighted(store)
    if graph.number_of_nodes() == 0:
        return []
    strengths: dict[str, float] = dict(graph.degree(weight="weight"))  # type: ignore[arg-type]
    ordered = sorted(strengths.items(), key=lambda kv: (-kv[1], kv[0]))
    return [WeightedStrength(nid, float(s)) for nid, s in ordered[: max(top, 0)]]

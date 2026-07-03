"""Composite importance ensemble over the entity graph (§3.14 / §17).

Ансамбль центральностей / centrality ensemble — a single ``importance`` ranking
that blends several classic centralities into one score. Each requested metric
is computed on the **undirected** ``:Entity`` projection (the same graph used by
community detection, §11 / §12.8), then **min-max normalised to ``[0, 1]``** and
finally averaged. The most-central entity — top of every normalised component —
earns a composite of ``1.0``.

Metrics available (all via NetworkX):

- ``degree`` — центральность по степени / degree centrality;
- ``closeness`` — центральность по близости / closeness centrality;
- ``betweenness`` — центральность по посредничеству / betweenness centrality;
- ``pagerank`` — PageRank стационарного распределения / stationary-mass PageRank.

Kuzu note: custom node props are not queryable columns, so the projection RETURNs
only base ``id`` columns (via :func:`project_entity_graph`) and never touches
``get_node``. Results are deterministic: ranked by composite descending, ties
broken by ``entity_id``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import networkx as nx
from networkx.algorithms.link_analysis.pagerank_alg import _pagerank_python

from kg_retrievers.graph_algos import project_entity_graph
from kg_retrievers.graph_store import KuzuGraphStore

# Requested-by-default blend — the full classic quartet.
DEFAULT_METRICS: tuple[str, ...] = ("degree", "closeness", "betweenness", "pagerank")


def _pagerank(graph: nx.Graph) -> dict[str, float]:
    """PageRank via NetworkX, robust to a missing SciPy — PageRank (§3.14).

    ``nx.pagerank`` delegates to a SciPy sparse solver; where SciPy is absent we
    fall back to NetworkX's own pure-python power iteration (same algorithm).
    """
    try:
        return nx.pagerank(graph)
    except (ImportError, ModuleNotFoundError):
        return _pagerank_python(graph)


# name -> raw (un-normalised) centrality over an undirected NetworkX graph.
_METRICS: dict[str, Callable[[nx.Graph], dict[str, float]]] = {
    "degree": nx.degree_centrality,
    "closeness": nx.closeness_centrality,
    "betweenness": nx.betweenness_centrality,
    "pagerank": _pagerank,
}


@dataclass(frozen=True)
class EnsembleScore:
    """One entity's composite importance and its per-metric breakdown (§3.14 / §17).

    ``entity_id`` — id узла-сущности / entity node id; ``composite`` — усреднённая
    важность в ``[0, 1]`` / averaged importance; ``components`` — min-max
    normalised value of each requested metric, keyed by metric name.
    """

    entity_id: str
    composite: float
    components: dict[str, float]

    def as_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "composite": self.composite,
            "components": dict(self.components),
        }


def _min_max(raw: dict[str, float]) -> dict[str, float]:
    """Min-max normalise a metric's values into ``[0, 1]`` — нормировка (§3.14).

    A flat metric (every value equal) carries no signal, so it collapses to
    ``0.0`` everywhere rather than dividing by a zero range.
    """
    if not raw:
        return {}
    lo, hi = min(raw.values()), max(raw.values())
    span = hi - lo
    if span == 0.0:
        return dict.fromkeys(raw, 0.0)
    return {nid: (val - lo) / span for nid, val in raw.items()}


def centrality_ensemble(
    store: KuzuGraphStore,
    top: int = 10,
    metrics: tuple[str, ...] = DEFAULT_METRICS,
) -> list[EnsembleScore]:
    """Blended importance ranking over the entity projection (§3.14 / §17).

    Each metric in ``metrics`` is computed on the undirected projection, min-max
    normalised to ``[0, 1]``, and the per-entity mean of those normalised values
    is the ``composite``. Returns up to ``top`` entities ranked by composite
    descending, ties broken by ``entity_id`` (deterministic across calls). An
    empty projection — or ``top <= 0`` — yields ``[]``.

    Raises ``KeyError`` for an unknown metric name.
    """
    graph = project_entity_graph(store)
    if graph.number_of_nodes() == 0:
        return []

    normalised = {name: _min_max(_METRICS[name](graph)) for name in metrics}

    scores: list[EnsembleScore] = []
    for nid in graph.nodes:
        components = {name: normalised[name][nid] for name in metrics}
        composite = sum(components.values()) / len(components) if components else 0.0
        scores.append(EnsembleScore(nid, composite, components))

    scores.sort(key=lambda s: (-s.composite, s.entity_id))
    return scores[: max(top, 0)]

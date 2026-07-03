"""Closeness & harmonic centrality over the entity graph (§3.14 / §12.8).

``graph_algos`` already ships degree- and betweenness-centrality plus a couple of
structural helpers, but it lacks the two classic *reach* metrics — how close an
entity sits to everything else. This module fills that gap by reusing the very
same undirected ``:Entity`` projection (:func:`project_entity_graph`) and exposing:

- ``closeness_centrality`` — центральность по близости: high when an entity can
  reach the rest of its component along short paths (NetworkX's Wasserman–Faust
  normalised closeness, in ``[0, 1]``);
- ``harmonic_centrality`` — гармоническая центральность: the sum of reciprocal
  distances ``Σ 1/d`` — a reach metric that stays finite on disconnected graphs.

Both are returned as frozen :class:`ClosenessScore` rows carrying *both* values,
so a single projection answers either ranking. Everything degrades gracefully on
an empty graph (``[]``).
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from kg_retrievers.graph_algos import project_entity_graph
from kg_retrievers.graph_store import KuzuGraphStore


@dataclass(frozen=True)
class ClosenessScore:
    """An entity id with its closeness & harmonic centrality (§3.14 / §12.8).

    ``closeness`` is the normalised closeness centrality in ``[0, 1]``;
    ``harmonic`` is the (unbounded) harmonic centrality ``Σ 1/d``.
    """

    entity_id: str
    closeness: float
    harmonic: float

    def as_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "closeness": self.closeness,
            "harmonic": self.harmonic,
        }


def _scores(store: KuzuGraphStore) -> dict[str, ClosenessScore]:
    """Compute both reach metrics for every projected entity — обе метрики (§12.8)."""
    graph = project_entity_graph(store)
    if graph.number_of_nodes() == 0:
        return {}
    closeness = nx.closeness_centrality(graph)
    harmonic = nx.harmonic_centrality(graph)
    return {
        nid: ClosenessScore(nid, float(closeness[nid]), float(harmonic[nid])) for nid in graph.nodes
    }


def closeness_centrality(store: KuzuGraphStore, top: int = 10) -> list[ClosenessScore]:
    """Top entities by closeness — центральность по близости (§3.14 / §12.8).

    Ranked by ``closeness`` descending, ties broken by ``entity_id`` for
    determinism. ``top <= 0`` or an empty graph yields ``[]``.
    """
    ranked = sorted(_scores(store).values(), key=lambda s: (-s.closeness, s.entity_id))
    return ranked[: max(top, 0)]


def harmonic_centrality(store: KuzuGraphStore, top: int = 10) -> list[ClosenessScore]:
    """Top entities by harmonic centrality — гармоническая центральность (§3.14 / §12.8).

    Ranked by ``harmonic`` descending, ties broken by ``entity_id``. Unlike
    closeness, this reach metric stays finite across disconnected components.
    ``top <= 0`` or an empty graph yields ``[]``.
    """
    ranked = sorted(_scores(store).values(), key=lambda s: (-s.harmonic, s.entity_id))
    return ranked[: max(top, 0)]

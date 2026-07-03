"""GDS-lite graph algorithms over the seed entity graph (§12.8).

Hand-checkable facts about the seed projection (see ``kg_retrievers.seed``):

- ``tech:catholyte-circulation-scheme`` (catholyte circulation) is the single
  most-connected entity: degree 4 (catholyte, nickel, expert, lab).
- The three desalination technologies (RO / ion-exchange / electrodialysis)
  each have exactly one neighbour — the mine water — so any two of them are a
  perfect neighbourhood match (Jaccard = 1.0).
- ``catholyte → circulation scheme → nickel`` is a 3-node shortest path.
- The water cluster and the nickel cluster are disconnected components.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_common import make_id
from kg_retrievers.graph_algos import (
    ScoredNode,
    betweenness_centrality,
    degree_centrality,
    shortest_path,
    similar_entities_by_neighbourhood,
)
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph

# Deterministic seed node ids (§24.2 make_id).
EW = make_id("TechnologySolution", "catholyte circulation scheme")
NI = make_id("Material", "nickel")
CATHOLYTE = make_id("Material", "catholyte nickel")
WATER = make_id("Material", "mine water concentrator feed")
RO = make_id("TechnologySolution", "reverse osmosis desalination")
IE = make_id("TechnologySolution", "ion exchange desalination")
ED = make_id("TechnologySolution", "electrodialysis desalination")


def _seed_store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(store)
    return store


def _empty_store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def test_degree_centrality_ranks_most_connected_first() -> None:
    store = _seed_store()
    try:
        ranked = degree_centrality(store, top=5)
        assert ranked, "seed graph must yield centrality scores"
        assert all(isinstance(s, ScoredNode) for s in ranked)
        # catholyte circulation (degree 4) is the unique most-connected entity.
        assert ranked[0].entity_id == EW
        # strictly ahead of the runner-up (degree 3).
        assert ranked[0].score > ranked[1].score
        assert ranked[0].as_dict() == {"entity_id": EW, "score": ranked[0].score}
    finally:
        store.close()


def test_degree_centrality_scores_are_normalised() -> None:
    store = _seed_store()
    try:
        ranked = degree_centrality(store, top=100)
        # normalised degree centrality lives in (0, 1]; scores are non-increasing.
        assert all(0.0 < s.score <= 1.0 for s in ranked)
        assert ranked == sorted(ranked, key=lambda s: -s.score)
    finally:
        store.close()


def test_betweenness_is_non_negative_and_bounded() -> None:
    store = _seed_store()
    try:
        ranked = betweenness_centrality(store, top=100)
        assert ranked
        assert all(0.0 <= s.score <= 1.0 for s in ranked)
        # the top hub also mediates paths, so it carries positive betweenness.
        assert ranked[0].score > 0.0
    finally:
        store.close()


def test_neighbourhood_similarity_self_excluded_and_bounded() -> None:
    store = _seed_store()
    try:
        sims = similar_entities_by_neighbourhood(store, RO, top=10)
        assert sims
        # RO never appears as similar to itself.
        assert all(s.entity_id != RO for s in sims)
        # Jaccard is bounded to [0, 1].
        assert all(0.0 <= s.score <= 1.0 for s in sims)
        # ion-exchange and electrodialysis share RO's only neighbour (mine water)
        # -> perfect neighbourhood match.
        perfect = {s.entity_id for s in sims if s.score == 1.0}
        assert perfect == {IE, ED}
    finally:
        store.close()


def test_shortest_path_between_connected_nodes() -> None:
    store = _seed_store()
    try:
        path = shortest_path(store, CATHOLYTE, NI)
        assert path[0] == CATHOLYTE
        assert path[-1] == NI
        # the only route runs through the circulation-scheme hub.
        assert path == [CATHOLYTE, EW, NI]
    finally:
        store.close()


def test_shortest_path_disconnected_pair_returns_empty() -> None:
    store = _seed_store()
    try:
        # water cluster vs nickel cluster are separate components.
        assert shortest_path(store, WATER, NI) == []
    finally:
        store.close()


def test_shortest_path_unknown_node_returns_empty() -> None:
    store = _seed_store()
    try:
        assert shortest_path(store, WATER, "material:does-not-exist") == []
    finally:
        store.close()


def test_empty_graph_is_graceful() -> None:
    store = _empty_store()
    try:
        assert degree_centrality(store) == []
        assert betweenness_centrality(store) == []
        assert similar_entities_by_neighbourhood(store, WATER) == []
        assert shortest_path(store, WATER, NI) == []
    finally:
        store.close()

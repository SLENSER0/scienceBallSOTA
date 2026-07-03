"""Retrieval scoring: evidence-quality, graph-proximity, weighted fusion (§12.4-12.6)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.scoring import (
    evidence_quality_score,
    graph_proximity_score,
    weighted_fuse,
)
from kg_retrievers.seed import build_seed_graph


@pytest.fixture(scope="module")
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(s)
    yield s
    s.close()


def test_evidence_quality_ordering() -> None:
    strong = evidence_quality_score(
        {"evidence_strength": "peer_reviewed", "confidence": 0.9, "verified": True}
    )
    weak = evidence_quality_score({"evidence_strength": "unverified", "confidence": 0.3})
    assert 0.0 <= weak < strong <= 1.0
    # verified boost
    base = evidence_quality_score({"evidence_strength": "patent", "confidence": 0.7})
    boosted = evidence_quality_score(
        {"evidence_strength": "patent", "confidence": 0.7, "review_status": "accepted"}
    )
    assert boosted > base


def test_graph_proximity_decays_with_distance(store: KuzuGraphStore) -> None:
    ro = make_id("TechnologySolution", "reverse osmosis desalination")
    neighbors = store.rows(
        "MATCH (n:Node {id:$id})-[:Rel]-(m:Node) RETURN m.id LIMIT 1", {"id": ro}
    )
    adjacent = neighbors[0][0]
    assert graph_proximity_score(store, ro, [ro]) == 1.0  # self
    assert graph_proximity_score(store, adjacent, [ro]) > 0.0  # 1 hop
    # an unrelated far node scores lower-or-equal than an adjacent one
    far = graph_proximity_score(store, make_id("Material", "nickel"), [ro], max_hops=1)
    assert far <= graph_proximity_score(store, adjacent, [ro])


def test_weighted_fuse_ranks_and_normalizes() -> None:
    comps = {
        "dense": {"a": 0.9, "b": 0.1, "c": 0.5},
        "keyword": {"a": 0.2, "b": 0.8},
        "graph_proximity": {"c": 1.0},
    }
    ranked = weighted_fuse(comps)
    ids = [f.id for f in ranked]
    assert set(ids) == {"a", "b", "c"}
    assert ranked == sorted(ranked, key=lambda f: f.score, reverse=True)
    # every fused score is a convex combination in [0,1]
    assert all(0.0 <= f.score <= 1.0 for f in ranked)
    # components recorded per candidate
    assert set(ranked[0].components) == {"dense", "keyword", "graph_proximity"}


def test_weighted_fuse_custom_weights_shift_ranking() -> None:
    comps = {"dense": {"x": 1.0, "y": 0.0}, "graph_proximity": {"x": 0.0, "y": 1.0}}
    dense_heavy = weighted_fuse(comps, {"dense": 0.9, "graph_proximity": 0.1})
    graph_heavy = weighted_fuse(comps, {"dense": 0.1, "graph_proximity": 0.9})
    assert dense_heavy[0].id == "x"
    assert graph_heavy[0].id == "y"

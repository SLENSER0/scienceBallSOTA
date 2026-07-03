"""PageRank & personalized PageRank tests (§3.14 / §17).

Hand-checkable graph over a fresh temp Kuzu store. Three entity nodes x, y, z
with edges x→z and y→z: z has in-degree 2, so it must rank first.

- len(pagerank(store)) == 3;
- the three scores sum to 1.0;
- pagerank(store)[0].entity_id == 'z' (highest in-degree);
- personalized_pagerank(store, ['x'])[0].entity_id == 'x';
- personalized_pagerank(store, ['nonexistent']) falls back to uniform (3 scores);
- an empty store returns [];
- results are deterministic and ties break by id.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_pagerank import (
    PageRankScore,
    pagerank,
    personalized_pagerank,
)
from kg_retrievers.graph_store import KuzuGraphStore


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def _node(store: KuzuGraphStore, nid: str) -> None:
    # 'Material' is in ENTITY_LABELS, so the node enters the projection.
    store.upsert_node(nid, "Material", name=nid)


def _fan_in_store() -> KuzuGraphStore:
    """x→z, y→z over three entity nodes; z has the highest in-degree."""
    store = _store()
    for nid in ("x", "y", "z"):
        _node(store, nid)
    store.upsert_edge("x", "z", "RELATED_TO")
    store.upsert_edge("y", "z", "RELATED_TO")
    return store


def test_pagerank_counts_all_entities() -> None:
    store = _fan_in_store()
    scores = pagerank(store)
    assert len(scores) == 3


def test_pagerank_scores_sum_to_one() -> None:
    store = _fan_in_store()
    total = sum(s.score for s in pagerank(store))
    assert total == pytest.approx(1.0, abs=1e-6)


def test_pagerank_highest_in_degree_first() -> None:
    store = _fan_in_store()
    assert pagerank(store)[0].entity_id == "z"


def test_personalized_pagerank_favours_seed() -> None:
    store = _fan_in_store()
    assert personalized_pagerank(store, ["x"])[0].entity_id == "x"


def test_personalized_pagerank_unknown_seed_falls_back_to_uniform() -> None:
    store = _fan_in_store()
    fallback = personalized_pagerank(store, ["nonexistent"])
    assert len(fallback) == 3
    # falling back to a uniform restart == plain PageRank
    assert [s.entity_id for s in fallback] == [s.entity_id for s in pagerank(store)]


def test_empty_store_returns_empty() -> None:
    store = _store()
    assert pagerank(store) == []
    assert personalized_pagerank(store, ["x"]) == []


def test_non_entity_edges_excluded() -> None:
    store = _store()
    for nid in ("x", "y", "z"):
        _node(store, nid)
    # a Document is NOT an entity label -> its edges must not enter the projection
    store.upsert_node("doc1", "Document", name="doc1")
    store.upsert_edge("x", "z", "RELATED_TO")
    store.upsert_edge("doc1", "z", "MENTIONS")
    ids = {s.entity_id for s in pagerank(store)}
    assert ids == {"x", "z"}
    assert "doc1" not in ids


def test_deterministic_and_tie_break_by_id() -> None:
    store = _fan_in_store()
    first = pagerank(store)
    second = pagerank(store)
    assert [s.as_dict() for s in first] == [s.as_dict() for s in second]
    # x and y are symmetric (each a single edge into z) -> equal score, id order
    tail = [s for s in first if s.entity_id in ("x", "y")]
    assert tail[0].score == pytest.approx(tail[1].score, abs=1e-9)
    assert [s.entity_id for s in tail] == ["x", "y"]


def test_score_dataclass_shape() -> None:
    s = PageRankScore(entity_id="x", score=0.5)
    assert s.as_dict() == {"entity_id": "x", "score": 0.5}

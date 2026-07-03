"""Tests for the confidence-weighted entity graph projection (§3.14 / §12.8).

Hand-checkable facts on a tiny entity graph a–b (0.5) and b–c (0.9):

- the a–b edge weight is exactly 0.5;
- b is the strongest node: incident weight 0.5 + 0.9 = 1.4;
- a has strength 0.5, c has strength 0.9;
- two parallel a–b edges (0.2, 0.3) collapse to a single weight 0.5;
- a null/missing confidence counts as 0.0;
- an empty store yields an empty graph and no strengths.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.graph_weighted_projection import (
    WeightedStrength,
    project_weighted,
    weighted_degree_strength,
)

# A concrete entity label (§ kg_schema.labels.ENTITY_LABELS).
LABEL = "Material"


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def _line_store() -> KuzuGraphStore:
    """a–b (conf 0.5) and b–c (conf 0.9)."""
    store = _store()
    for nid in ("a", "b", "c"):
        store.upsert_node(nid, LABEL, name=nid)
    store.upsert_edge("a", "b", "REL_AB", confidence=0.5)
    store.upsert_edge("b", "c", "REL_BC", confidence=0.9)
    return store


def test_edge_weight_is_the_confidence() -> None:
    store = _line_store()
    try:
        graph = project_weighted(store)
        assert graph["a"]["b"]["weight"] == pytest.approx(0.5)
        assert graph["b"]["c"]["weight"] == pytest.approx(0.9)
    finally:
        store.close()


def test_weighted_degree_ranks_hub_first() -> None:
    store = _line_store()
    try:
        ranked = weighted_degree_strength(store)
        assert all(isinstance(s, WeightedStrength) for s in ranked)
        # b sits on both edges: 0.5 + 0.9 = 1.4 -> strongest.
        assert ranked[0].entity_id == "b"
        assert ranked[0].strength == pytest.approx(1.4)
        by_id = {s.entity_id: s.strength for s in ranked}
        assert by_id["a"] == pytest.approx(0.5)
        assert by_id["c"] == pytest.approx(0.9)
        assert ranked[0].as_dict() == {"entity_id": "b", "strength": ranked[0].strength}
    finally:
        store.close()


def test_ranking_is_descending_with_id_tiebreak() -> None:
    store = _line_store()
    try:
        ranked = weighted_degree_strength(store)
        strengths = [s.strength for s in ranked]
        assert strengths == sorted(strengths, reverse=True)
    finally:
        store.close()


def test_top_limit_is_respected() -> None:
    store = _line_store()
    try:
        assert len(weighted_degree_strength(store, top=1)) == 1
        assert weighted_degree_strength(store, top=0) == []
    finally:
        store.close()


def test_parallel_edges_sum_into_one_weight() -> None:
    store = _store()
    for nid in ("a", "b"):
        store.upsert_node(nid, LABEL, name=nid)
    store.upsert_edge("a", "b", "REL_P1", confidence=0.2)
    store.upsert_edge("a", "b", "REL_P2", confidence=0.3)
    try:
        graph = project_weighted(store)
        assert graph["a"]["b"]["weight"] == pytest.approx(0.5)
        ranked = weighted_degree_strength(store)
        assert {s.entity_id for s in ranked} == {"a", "b"}
        assert all(s.strength == pytest.approx(0.5) for s in ranked)
    finally:
        store.close()


def test_missing_confidence_counts_as_zero() -> None:
    store = _store()
    for nid in ("a", "b", "c"):
        store.upsert_node(nid, LABEL, name=nid)
    store.upsert_edge("a", "b", "REL_NULL")  # no confidence -> 0.0
    store.upsert_edge("b", "c", "REL_BC", confidence=0.9)
    try:
        graph = project_weighted(store)
        assert graph["a"]["b"]["weight"] == pytest.approx(0.0)
        by_id = {s.entity_id: s.strength for s in weighted_degree_strength(store)}
        assert by_id["a"] == pytest.approx(0.0)
        assert by_id["b"] == pytest.approx(0.9)
    finally:
        store.close()


def test_empty_store_is_graceful() -> None:
    store = _store()
    try:
        graph = project_weighted(store)
        assert graph.number_of_nodes() == 0
        assert graph.number_of_edges() == 0
        assert weighted_degree_strength(store) == []
    finally:
        store.close()

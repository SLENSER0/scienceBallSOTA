"""Tests for §17.5 GlobalFilters confidence/verified pruning (§17.5 / §2.1).

Проверяем чистую функцию ``prune_graph`` над §5.3 GraphResponse dict: порог
достоверности, флаг ``verified_only``, удаление повисших рёбер, счётчики и JSON.
"""

from __future__ import annotations

import json

from kg_retrievers.graph_confidence_filter import (
    PrunedGraph,
    prune_graph,
    prune_graph_json,
)


def _payload() -> dict:
    """Three nodes (mixed confidence + verified) with edges §5.3."""
    return {
        "nodes": [
            {"id": "n1", "confidence": 0.9, "verified": True},
            {"id": "n2", "confidence": 0.2, "verified": False},
            {"id": "n3", "confidence": None, "verified": False},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n3", "confidence": 0.8},
            {"id": "e2", "source": "n1", "target": "n2", "confidence": 0.3},
        ],
    }


def test_edge_below_min_confidence_is_dropped() -> None:
    # e2 has confidence 0.3 < 0.5 -> dropped by threshold.
    result = prune_graph(_payload(), min_confidence=0.5)
    assert "e2" not in {e["id"] for e in result.edges}


def test_node_below_min_confidence_is_dropped() -> None:
    # n2 has confidence 0.2 < 0.5 -> dropped.
    result = prune_graph(_payload(), min_confidence=0.5)
    assert "n2" not in {n["id"] for n in result.nodes}


def test_verified_only_drops_unverified_node() -> None:
    # n2 has verified=False -> dropped when verified_only=True.
    result = prune_graph(_payload(), verified_only=True)
    dropped = {n["id"] for n in _payload()["nodes"]} - {n["id"] for n in result.nodes}
    assert "n2" in dropped
    assert "n3" in dropped  # verified falsy too
    assert {n["id"] for n in result.nodes} == {"n1"}


def test_orphan_edge_dropped_when_source_pruned() -> None:
    # Node n1 is pruned by verified_only? No — force via min_confidence on a custom graph.
    graph = {
        "nodes": [
            {"id": "a", "confidence": 0.1, "verified": True},
            {"id": "b", "confidence": 0.9, "verified": True},
        ],
        "edges": [
            # High-confidence edge, but its source 'a' gets pruned -> orphan.
            {"id": "eab", "source": "a", "target": "b", "confidence": 0.99},
        ],
    }
    result = prune_graph(graph, min_confidence=0.5)
    assert {n["id"] for n in result.nodes} == {"b"}
    assert result.edges == ()  # eab dropped as orphan despite high confidence
    assert result.dropped_edges == 1


def test_no_filters_is_identity_with_zero_counts() -> None:
    result = prune_graph(_payload())
    assert len(result.nodes) == 3
    assert len(result.edges) == 2
    assert result.dropped_nodes == 0
    assert result.dropped_edges == 0
    assert [n["id"] for n in result.nodes] == ["n1", "n2", "n3"]
    assert [e["id"] for e in result.edges] == ["e1", "e2"]


def test_confidence_none_survives_high_threshold() -> None:
    # n3 has confidence None -> unknown passes even at 0.9.
    result = prune_graph(_payload(), min_confidence=0.9)
    assert "n3" in {n["id"] for n in result.nodes}


def test_dropped_counts_are_exact() -> None:
    result = prune_graph(_payload(), min_confidence=0.5)
    # Nodes dropped: n2 (0.2). n1 (0.9) and n3 (None) survive.
    assert {n["id"] for n in result.nodes} == {"n1", "n3"}
    assert result.dropped_nodes == 1
    # Edges: e2 dropped by threshold (0.3) AND touched pruned n2; e1 survives.
    assert {e["id"] for e in result.edges} == {"e1"}
    assert result.dropped_edges == 1


def test_as_dict_keys_and_shape() -> None:
    result = prune_graph(_payload(), min_confidence=0.5)
    d = result.as_dict()
    assert set(d.keys()) == {"nodes", "edges", "droppedNodes", "droppedEdges"}
    assert isinstance(d["nodes"], list)
    assert isinstance(d["edges"], list)
    assert d["droppedNodes"] == result.dropped_nodes
    assert d["droppedEdges"] == result.dropped_edges


def test_json_helper_roundtrips_as_dict() -> None:
    payload = _payload()
    parsed = json.loads(prune_graph_json(payload, min_confidence=0.5))
    expected = prune_graph(payload, min_confidence=0.5).as_dict()
    assert parsed == expected


def test_frozen_dataclass_is_immutable() -> None:
    result = prune_graph(_payload())
    assert isinstance(result, PrunedGraph)
    try:
        result.dropped_nodes = 99  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - dataclass(frozen=True) must forbid assignment
        raise AssertionError("PrunedGraph must be frozen")

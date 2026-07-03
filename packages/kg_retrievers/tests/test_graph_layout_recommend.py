"""Tests for the §17.8 Reagraph layoutType recommender (pure, no store)."""

from __future__ import annotations

from kg_retrievers.graph_layout_recommend import (
    LAYOUT_CIRCULAR,
    LAYOUT_FORCE_2D,
    LAYOUT_HIERARCHICAL,
    LAYOUT_RADIAL,
    LayoutRecommendation,
    recommend_reagraph_layout,
)


def _graph(node_ids: list[str], edges: list[tuple[str, str]]) -> dict:
    """Build a materialised graph dict from node ids and (source, target) pairs."""
    return {
        "nodes": [{"id": nid} for nid in node_ids],
        "edges": [{"source": s, "target": t} for s, t in edges],
    }


def test_four_node_three_edge_tree_is_hierarchical() -> None:
    # a -> b -> c and a -> d : connected tree, 4 nodes / 3 edges.
    graph = _graph(["a", "b", "c", "d"], [("a", "b"), ("b", "c"), ("a", "d")])
    rec = recommend_reagraph_layout(graph)
    assert rec.layout == LAYOUT_HIERARCHICAL
    assert rec.is_tree is True
    assert rec.node_count == 4
    assert rec.edge_count == 3


def test_star_with_root_ids_is_radial() -> None:
    # 1 hub incident to all 5 edges (100% >= 60%) + 5 leaves, root_ids=[hub].
    edges = [("hub", f"leaf{i}") for i in range(5)]
    graph = _graph(["hub", "leaf0", "leaf1", "leaf2", "leaf3", "leaf4"], edges)
    rec = recommend_reagraph_layout(graph, root_ids=["hub"])
    assert rec.layout == LAYOUT_RADIAL
    # A star is topologically a tree, but the hub+root_ids radial rule wins first.
    assert rec.is_tree is True  # 5 edges == 6 - 1
    assert rec.node_count == 6
    assert rec.edge_count == 5


def test_star_without_root_ids_is_hierarchical_tree() -> None:
    # Same star but no root_ids -> radial gate closed; a 6-node/5-edge star is a
    # tree (5 == 6 - 1) so the tree rule yields hierarchical.
    edges = [("hub", f"leaf{i}") for i in range(5)]
    graph = _graph(["hub", "leaf0", "leaf1", "leaf2", "leaf3", "leaf4"], edges)
    rec = recommend_reagraph_layout(graph)
    assert rec.layout == LAYOUT_HIERARCHICAL
    assert rec.is_tree is True


def test_small_cyclic_non_tree_is_circular() -> None:
    # 6 nodes / 8 edges, cyclic, no single dominant hub -> circular.
    node_ids = ["n0", "n1", "n2", "n3", "n4", "n5"]
    edges = [
        ("n0", "n1"),
        ("n1", "n2"),
        ("n2", "n3"),
        ("n3", "n4"),
        ("n4", "n5"),
        ("n5", "n0"),  # 6-cycle
        ("n0", "n3"),  # chords
        ("n1", "n4"),
    ]
    graph = _graph(node_ids, edges)
    rec = recommend_reagraph_layout(graph, root_ids=["n0"])
    # No hub reaches 60% of 8 edges (max incidence 3 < 4.8) so radial is not chosen.
    assert rec.layout == LAYOUT_CIRCULAR
    assert rec.is_tree is False
    assert rec.node_count == 6
    assert rec.edge_count == 8


def test_large_dense_graph_is_force_directed() -> None:
    # 40 nodes / 120 edges, not a tree, no root_ids, > 12 nodes -> forceDirected2d.
    node_ids = [f"n{i}" for i in range(40)]
    edges = [(f"n{i % 40}", f"n{(i * 7 + 3) % 40}") for i in range(120)]
    graph = _graph(node_ids, edges)
    rec = recommend_reagraph_layout(graph)
    assert rec.layout == LAYOUT_FORCE_2D
    assert rec.node_count == 40
    assert rec.edge_count == 120


def test_node_and_edge_counts_echo_input_sizes() -> None:
    graph = _graph(["x", "y", "z"], [("x", "y")])
    rec = recommend_reagraph_layout(graph)
    assert rec.node_count == 3
    assert rec.edge_count == 1


def test_empty_graph_is_force_directed_and_not_tree() -> None:
    rec = recommend_reagraph_layout({"nodes": [], "edges": []})
    assert rec.layout == LAYOUT_FORCE_2D
    assert rec.is_tree is False
    assert rec.node_count == 0
    assert rec.edge_count == 0


def test_missing_keys_treated_as_empty() -> None:
    rec = recommend_reagraph_layout({})
    assert rec.layout == LAYOUT_FORCE_2D
    assert rec.is_tree is False


def test_as_dict_camelcase_and_is_tree_is_bool() -> None:
    graph = _graph(["a", "b"], [("a", "b")])  # 2 nodes / 1 edge -> tree
    rec = recommend_reagraph_layout(graph)
    payload = rec.as_dict()
    assert payload == {
        "layout": LAYOUT_HIERARCHICAL,
        "reason": rec.reason,
        "nodeCount": 2,
        "edgeCount": 1,
        "isTree": True,
    }
    assert isinstance(payload["isTree"], bool)


def test_recommendation_is_frozen() -> None:
    rec = recommend_reagraph_layout({"nodes": [], "edges": []})
    assert isinstance(rec, LayoutRecommendation)
    try:
        rec.layout = "x"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("LayoutRecommendation must be frozen")

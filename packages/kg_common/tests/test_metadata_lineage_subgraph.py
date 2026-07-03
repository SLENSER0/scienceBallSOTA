"""Tests for the bounded-hop lineage subgraph builder — тесты линидж-подграфа (§10.7)."""

from __future__ import annotations

from kg_common.metadata.lineage_subgraph import (
    LineageNode,
    LineageSubgraph,
    build_subgraph,
)


def _roles(sub: LineageSubgraph) -> dict[str, tuple[str, int]]:
    """Map ``id -> (role, depth)`` for hand-checking — карта ролей узлов."""
    return {n.id: (n.role, n.depth) for n in sub.nodes}


def test_isolated_focus_single_node_no_edges() -> None:
    # Focus absent from every edge → one 'focus' node at depth 0, no edges.
    sub = build_subgraph([("X", "Y"), ("Y", "Z")], "B")
    assert sub.focus == "B"
    assert sub.nodes == (LineageNode("B", "focus", 0),)
    assert sub.edges == ()


def test_line_up1_down1_roles_and_depths() -> None:
    # A -> B -> C with focus B, one hop each way → A upstream/1, B focus/0, C downstream/1.
    sub = build_subgraph([("A", "B"), ("B", "C")], "B", up_hops=1, down_hops=1)
    assert _roles(sub) == {
        "A": ("upstream", 1),
        "B": ("focus", 0),
        "C": ("downstream", 1),
    }
    # Sorted by (role, depth, id): upstream < focus < downstream.
    assert [n.id for n in sub.nodes] == ["A", "B", "C"]


def test_up_hops_zero_excludes_upstream() -> None:
    # up_hops=0 drops every upstream node; downstream still present.
    sub = build_subgraph([("A", "B"), ("B", "C")], "B", up_hops=0, down_hops=1)
    assert "A" not in _roles(sub)
    assert _roles(sub) == {"B": ("focus", 0), "C": ("downstream", 1)}
    # Edge A->B is dropped because A is excluded; B->C remains.
    assert sub.edges == (("B", "C"),)


def test_downstream_hop_bound_stops_at_depth() -> None:
    # A -> B -> C -> D, focus A, down_hops=2 → B(1), C(2) included, D(3) excluded.
    sub = build_subgraph([("A", "B"), ("B", "C"), ("C", "D")], "A", down_hops=2)
    roles = _roles(sub)
    assert roles["B"] == ("downstream", 1)
    assert roles["C"] == ("downstream", 2)
    assert "D" not in roles
    assert roles["A"] == ("focus", 0)


def test_every_edge_connects_included_nodes() -> None:
    edges = [("A", "B"), ("B", "C"), ("C", "D"), ("X", "A")]
    sub = build_subgraph(edges, "B", up_hops=1, down_hops=1)
    included = {n.id for n in sub.nodes}
    for src, tgt in sub.edges:
        assert src in included and tgt in included
    # X is 2 hops upstream (X->A->B) so excluded at up_hops=1; edge X->A dropped.
    assert ("X", "A") not in sub.edges


def test_diamond_downstream_includes_all_descendants() -> None:
    # A -> B, A -> C, B -> D, C -> D; focus A → B, C, D all downstream.
    edges = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]
    sub = build_subgraph(edges, "A", down_hops=2)
    roles = _roles(sub)
    assert roles["A"] == ("focus", 0)
    assert roles["B"] == ("downstream", 1)
    assert roles["C"] == ("downstream", 1)
    assert roles["D"] == ("downstream", 2)
    # All four diamond edges connect included nodes and are sorted.
    assert sub.edges == (("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"))


def test_focus_appears_exactly_once() -> None:
    edges = [("A", "B"), ("B", "C"), ("C", "A")]  # cycle touching focus twice
    sub = build_subgraph(edges, "A", up_hops=2, down_hops=2)
    focus_nodes = [n for n in sub.nodes if n.role == "focus"]
    assert len(focus_nodes) == 1
    assert focus_nodes[0] == LineageNode("A", "focus", 0)
    # Exactly one node carries id == focus.
    assert sum(1 for n in sub.nodes if n.id == "A") == 1


def test_as_dict_shapes() -> None:
    sub = build_subgraph([("A", "B"), ("B", "C")], "B", up_hops=1, down_hops=1)
    assert LineageNode("A", "upstream", 1).as_dict() == {
        "id": "A",
        "role": "upstream",
        "depth": 1,
    }
    d = sub.as_dict()
    assert d["focus"] == "B"
    assert {"id": "B", "role": "focus", "depth": 0} in d["nodes"]
    assert ["B", "C"] in d["edges"]

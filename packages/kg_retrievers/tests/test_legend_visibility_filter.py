"""Tests for the Graph Explorer legend visibility toggle filter (§17.8).

RU: Проверяет применение переключателей легенды к конкретному графу.
EN: Verifies applying legend toggles to a concrete graph.
"""

from __future__ import annotations

from kg_retrievers.legend_visibility_filter import (
    FilteredGraph,
    VisibilityState,
    apply_visibility,
)


def _sample_graph() -> dict:
    """A small hand-checkable graph with 4 nodes and 4 edges (§17.8).

    Nodes: material ``m1``, property ``p1``, gap ``g1``, study ``s1``.
    Edges:
      * ``m1 -MEASURED_PROPERTY-> p1``  (observed)
      * ``m1 -HAS_GAP-> g1``            (touches the gap node)
      * ``s1 -SUPPORTS-> p1``           (inferred=True)
      * ``s1 -REFUTES-> p1``            (contradicted=True)
    """
    return {
        "nodes": [
            {"id": "m1", "type": "Material", "label": "TiO2"},
            {"id": "p1", "type": "Property", "label": "band gap"},
            {"id": "g1", "type": "Gap", "label": "missing conductivity"},
            {"id": "s1", "type": "Study", "label": "Doe 2024"},
        ],
        "edges": [
            {"id": "e1", "source": "m1", "target": "p1", "type": "MEASURED_PROPERTY"},
            {"id": "e2", "source": "m1", "target": "g1", "type": "HAS_GAP"},
            {"id": "e3", "source": "s1", "target": "p1", "type": "SUPPORTS", "inferred": True},
            {"id": "e4", "source": "s1", "target": "p1", "type": "REFUTES", "contradicted": True},
        ],
    }


def test_default_state_returns_graph_unchanged() -> None:
    """Default VisibilityState hides nothing; counts are 0 (§17.8)."""
    graph = _sample_graph()
    result = apply_visibility(graph, VisibilityState((), (), True, True))
    assert isinstance(result, FilteredGraph)
    assert len(result.nodes) == 4
    assert len(result.edges) == 4
    assert result.hidden_node_count == 0
    assert result.hidden_edge_count == 0
    # Surviving elements are exactly the input elements.
    assert [n["id"] for n in result.nodes] == ["m1", "p1", "g1", "s1"]
    assert [e["id"] for e in result.edges] == ["e1", "e2", "e3", "e4"]


def test_default_state_is_the_dataclass_default() -> None:
    """VisibilityState() equals the neutral toggle state (§17.8)."""
    assert VisibilityState() == VisibilityState((), (), True, True)


def test_hiding_gap_node_removes_node_and_incident_edge() -> None:
    """Hiding node type 'Gap' removes g1 and its incident edge e2 (§17.8)."""
    graph = _sample_graph()
    result = apply_visibility(graph, VisibilityState(hidden_node_types=("Gap",)))
    node_ids = [n["id"] for n in result.nodes]
    assert "g1" not in node_ids
    assert node_ids == ["m1", "p1", "s1"]
    assert result.hidden_node_count == 1
    # e2 (m1 -> g1) is incident to the hidden node and must be removed.
    edge_ids = [e["id"] for e in result.edges]
    assert "e2" not in edge_ids
    assert result.hidden_edge_count == 1


def test_hidden_node_count_counts_only_removed_nodes() -> None:
    """hidden_node_count reflects the number of dropped nodes (§17.8)."""
    graph = _sample_graph()
    result = apply_visibility(graph, VisibilityState(hidden_node_types=("Gap", "Study")))
    assert result.hidden_node_count == 2
    assert [n["id"] for n in result.nodes] == ["m1", "p1"]
    # Study s1 is endpoint of e3 and e4; Gap g1 of e2 -> 3 edges removed.
    assert result.hidden_edge_count == 3
    assert [e["id"] for e in result.edges] == ["e1"]


def test_hidden_edge_type_removes_edges_keeps_endpoint_nodes() -> None:
    """Hiding edge type MEASURED_PROPERTY drops e1 but keeps m1/p1 (§17.8)."""
    graph = _sample_graph()
    result = apply_visibility(graph, VisibilityState(hidden_edge_types=("MEASURED_PROPERTY",)))
    edge_ids = [e["id"] for e in result.edges]
    assert "e1" not in edge_ids
    assert result.hidden_edge_count == 1
    assert result.hidden_node_count == 0
    # Endpoint nodes of the hidden edge survive.
    node_ids = [n["id"] for n in result.nodes]
    assert "m1" in node_ids
    assert "p1" in node_ids
    assert len(result.nodes) == 4


def test_show_inferred_false_removes_inferred_edge() -> None:
    """show_inferred=False removes the inferred edge e3 (§17.8)."""
    graph = _sample_graph()
    result = apply_visibility(graph, VisibilityState(show_inferred=False))
    edge_ids = [e["id"] for e in result.edges]
    assert "e3" not in edge_ids
    assert result.hidden_edge_count == 1
    # The contradicted edge e4 stays because show_contradicted defaults True.
    assert "e4" in edge_ids


def test_show_contradicted_true_keeps_contradicted_edge() -> None:
    """show_contradicted=True keeps the contradicted edge e4 (§17.8)."""
    graph = _sample_graph()
    result = apply_visibility(graph, VisibilityState(show_contradicted=True))
    edge_ids = [e["id"] for e in result.edges]
    assert "e4" in edge_ids
    assert result.hidden_edge_count == 0


def test_show_contradicted_false_removes_contradicted_edge() -> None:
    """show_contradicted=False removes the contradicted edge e4 (§17.8)."""
    graph = _sample_graph()
    result = apply_visibility(graph, VisibilityState(show_contradicted=False))
    edge_ids = [e["id"] for e in result.edges]
    assert "e4" not in edge_ids
    assert result.hidden_edge_count == 1
    assert "e3" in edge_ids  # inferred edge stays


def test_edge_hidden_for_multiple_reasons_counted_once() -> None:
    """An edge both inferred and incident to a hidden node counts once (§17.8)."""
    graph = {
        "nodes": [
            {"id": "a", "type": "Material"},
            {"id": "b", "type": "Gap"},
        ],
        "edges": [
            {"id": "x", "source": "a", "target": "b", "type": "HAS_GAP", "inferred": True},
        ],
    }
    result = apply_visibility(
        graph,
        VisibilityState(hidden_node_types=("Gap",), show_inferred=False),
    )
    assert result.hidden_edge_count == 1
    assert result.edges == ()
    assert result.hidden_node_count == 1


def test_as_dict_round_trips_state_and_graph() -> None:
    """as_dict() exposes plain-dict views for state and result (§17.8)."""
    state = VisibilityState(("Gap",), ("REFUTES",), False, True)
    assert state.as_dict() == {
        "hidden_node_types": ["Gap"],
        "hidden_edge_types": ["REFUTES"],
        "show_inferred": False,
        "show_contradicted": True,
    }
    result = apply_visibility(_sample_graph(), state)
    d = result.as_dict()
    assert d["hidden_node_count"] == 1
    # e2 (-> g1 hidden node), e4 (REFUTES type), e3 (inferred) all removed.
    assert d["hidden_edge_count"] == 3
    assert [e["id"] for e in d["edges"]] == ["e1"]
    assert [n["id"] for n in d["nodes"]] == ["m1", "p1", "s1"]


def test_empty_graph_yields_empty_filtered_graph() -> None:
    """An empty graph produces empty results and zero counts (§17.8)."""
    result = apply_visibility({}, VisibilityState())
    assert result.nodes == ()
    assert result.edges == ()
    assert result.hidden_node_count == 0
    assert result.hidden_edge_count == 0

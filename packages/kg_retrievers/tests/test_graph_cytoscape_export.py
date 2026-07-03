"""Tests for Cytoscape.js elements JSON export (§22.6)."""

from __future__ import annotations

import json

from kg_retrievers.graph_cytoscape_export import (
    CytoscapeGraph,
    edge_element,
    node_element,
    to_cytoscape,
    to_json,
)


def test_empty_graph_shape() -> None:
    """(1) Empty graph → the canonical empty elements envelope."""
    graph = to_cytoscape([], [])
    assert isinstance(graph, CytoscapeGraph)
    assert graph.as_dict() == {"elements": {"nodes": [], "edges": []}}


def test_node_element_label_from_name() -> None:
    """(2) Node id='m1' name='Al' → label taken from name."""
    assert node_element({"id": "m1", "name": "Al"}) == {"data": {"id": "m1", "label": "Al"}}


def test_node_props_nested_under_data() -> None:
    """(3) Custom node props are nested under ``data`` verbatim."""
    element = node_element({"id": "m1", "name": "Al", "hardness": 5})
    assert element["data"]["hardness"] == 5
    assert element["data"]["id"] == "m1"
    assert element["data"]["label"] == "Al"


def test_edge_element_source_target_and_id() -> None:
    """(4) Edge s→t → data.source/target and a 's-<type>-t' id."""
    element = edge_element({"source": "s", "target": "t", "type": "bonds_with"})
    assert element["data"]["source"] == "s"
    assert element["data"]["target"] == "t"
    assert element["data"]["id"] == "s-bonds_with-t"


def test_edge_label_equals_rel_type() -> None:
    """(5) Edge label equals the relationship type."""
    element = edge_element({"source": "a", "target": "b", "type": "REACTS_WITH"})
    assert element["data"]["label"] == "REACTS_WITH"


def test_to_json_round_trips() -> None:
    """(6) to_json emits valid JSON that parses back to the same dict."""
    nodes = [{"id": "m1", "name": "Al"}, {"id": "m2", "name": "Fe"}]
    edges = [{"source": "m1", "target": "m2", "type": "harder_than"}]
    text = to_json(nodes, edges)
    parsed = json.loads(text)
    assert parsed == to_cytoscape(nodes, edges).as_dict()


def test_node_missing_name_falls_back_to_id() -> None:
    """(7) Node without a name → label falls back to the id."""
    assert node_element({"id": "x9"}) == {"data": {"id": "x9", "label": "x9"}}


def test_edge_count_preserved() -> None:
    """(8) Output edge count equals the number of input edges."""
    edges = [
        {"source": "a", "target": "b", "type": "r1"},
        {"source": "b", "target": "c", "type": "r2"},
        {"source": "c", "target": "a", "type": "r3"},
    ]
    graph = to_cytoscape([{"id": "a"}, {"id": "b"}, {"id": "c"}], edges)
    assert len(graph.as_dict()["elements"]["edges"]) == len(edges)


def test_indent_produces_pretty_json() -> None:
    """to_json indent kwarg yields multi-line pretty JSON that still round-trips."""
    nodes = [{"id": "m1", "name": "Медь"}]
    text = to_json(nodes, [], indent=2)
    assert "\n" in text
    # ensure_ascii=False keeps кириллица verbatim.
    assert "Медь" in text
    assert json.loads(text) == to_cytoscape(nodes, []).as_dict()


def test_edge_explicit_id_preserved() -> None:
    """An explicit edge id overrides the derived 's-<type>-t' id."""
    element = edge_element({"id": "e42", "source": "s", "target": "t", "type": "rel"})
    assert element["data"]["id"] == "e42"


def test_edge_extra_props_nested() -> None:
    """Custom edge props are nested under ``data`` verbatim."""
    element = edge_element({"source": "s", "target": "t", "type": "rel", "weight": 0.7})
    assert element["data"]["weight"] == 0.7

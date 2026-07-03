"""Tests for the §22.6 Cypher CREATE dump serializer (hand-checked literals)."""

from __future__ import annotations

from kg_retrievers.graph_cypher_dump import (
    CypherDump,
    _cypher_value,
    _props_map,
    node_create,
    rel_create,
    script_text,
    to_cypher,
)


def test_node_create_id_then_name() -> None:
    """(1) label→:Material, props id then name in order."""
    node = {"id": "m1", "label": "Material", "name": "Al"}
    assert node_create(node) == "CREATE (:Material {id: 'm1', name: 'Al'});"


def test_string_apostrophe_is_escaped() -> None:
    """(2) an apostrophe in a string prop is backslash-escaped."""
    assert _cypher_value("O'Brien") == "'O\\'Brien'"
    node = {"id": "p1", "label": "Person", "name": "O'Brien"}
    assert node_create(node) == "CREATE (:Person {id: 'p1', name: 'O\\'Brien'});"


def test_numeric_props_rendered_without_quotes() -> None:
    """(3) int/float props are bare; bool renders true/false (not quoted)."""
    assert _cypher_value(42) == "42"
    assert _cypher_value(1.5) == "1.5"
    assert _cypher_value(True) == "true"
    assert _cypher_value(False) == "false"
    node = {"id": "x", "label": "Measurement", "value": 42, "ratio": 1.5}
    assert node_create(node) == "CREATE (:Measurement {id: 'x', value: 42, ratio: 1.5});"


def test_none_valued_prop_is_omitted() -> None:
    """(4) a None-valued property drops out of the map entirely."""
    assert _cypher_value(None) is None
    assert _props_map({"id": "m1", "unit": None, "name": "Al"}) == "{id: 'm1', name: 'Al'}"
    node = {"id": "m1", "label": "Material", "name": "Al", "unit": None}
    assert node_create(node) == "CREATE (:Material {id: 'm1', name: 'Al'});"


def test_rel_create_match_create_by_id() -> None:
    """(5) relationship matched by endpoint id, then created with the given type."""
    edge = {"source": "s", "target": "t", "type": "HAS_PROPERTY"}
    expected = "MATCH (a {id: 's'}), (b {id: 't'}) CREATE (a)-[:HAS_PROPERTY]->(b)"
    assert expected in rel_create(edge)
    assert rel_create(edge).endswith(";")


def test_rel_create_carries_extra_props() -> None:
    """Extra edge keys become relationship properties inside the arrow."""
    edge = {"source": "s", "target": "t", "type": "SUPPORTS", "confidence": 0.9}
    out = rel_create(edge)
    expected = "MATCH (a {id: 's'}), (b {id: 't'}) CREATE (a)-[:SUPPORTS {confidence: 0.9}]->(b);"
    assert out == expected


def test_script_lists_all_nodes_before_rels() -> None:
    """(6) every node CREATE precedes every relationship MATCH..CREATE."""
    nodes = [
        {"id": "s", "label": "Material", "name": "Al"},
        {"id": "t", "label": "Property", "name": "Strength"},
    ]
    edges = [{"source": "s", "target": "t", "type": "HAS_PROPERTY"}]
    dump = to_cypher(nodes, edges)
    lines = dump.script.splitlines()
    assert lines == [
        "CREATE (:Material {id: 's', name: 'Al'});",
        "CREATE (:Property {id: 't', name: 'Strength'});",
        "MATCH (a {id: 's'}), (b {id: 't'}) CREATE (a)-[:HAS_PROPERTY]->(b);",
    ]
    last_node_idx = max(i for i, line in enumerate(lines) if line.startswith("CREATE (:"))
    first_rel_idx = min(i for i, line in enumerate(lines) if line.startswith("MATCH"))
    assert last_node_idx < first_rel_idx


def test_node_without_label_uses_default() -> None:
    """(7) a node dict with no label falls back to :Node."""
    assert node_create({"id": "n1", "name": "x"}) == "CREATE (:Node {id: 'n1', name: 'x'});"
    assert node_create({"id": "n2", "label": None}) == "CREATE (:Node {id: 'n2'});"


def test_empty_input_yields_empty_script() -> None:
    """(8) no nodes and no edges → empty script string."""
    assert script_text([], []) == ""
    dump = to_cypher([], [])
    assert dump.node_stmts == ()
    assert dump.rel_stmts == ()
    assert dump.script == ""


def test_cypher_dump_as_dict_roundtrip() -> None:
    """CypherDump is a frozen dataclass exposing a JSON-ready as_dict()."""
    nodes = [{"id": "s", "label": "Material", "name": "Al"}]
    edges = [{"source": "s", "target": "s", "type": "SELF"}]
    dump = to_cypher(nodes, edges)
    assert isinstance(dump, CypherDump)
    payload = dump.as_dict()
    assert payload["node_stmts"] == ["CREATE (:Material {id: 's', name: 'Al'});"]
    assert payload["rel_stmts"] == ["MATCH (a {id: 's'}), (b {id: 's'}) CREATE (a)-[:SELF]->(b);"]
    assert payload["script"] == dump.script
    assert isinstance(payload["node_stmts"], list)


def test_script_text_matches_to_cypher_script() -> None:
    """script_text is a thin wrapper over to_cypher(...).script."""
    nodes = [{"id": "a", "label": "X", "name": "a"}]
    edges: list[dict[str, object]] = []
    assert script_text(nodes, edges) == to_cypher(nodes, edges).script
    assert script_text(nodes, edges) == "CREATE (:X {id: 'a', name: 'a'});"

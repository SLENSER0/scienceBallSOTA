"""Tests for §22.6 GraphML graph serialization (hand-checkable assertions)."""

from __future__ import annotations

from kg_retrievers.graph_graphml_export import (
    GraphMLDoc,
    GraphMLKey,
    collect_keys,
    graphml_document,
    nodes_edges_to_graphml,
)


def test_empty_input_has_graphml_and_directed_graph_but_no_node() -> None:
    """(1) empty in -> contains '<graphml' and directed '<graph>' and no '<node>'."""
    doc = nodes_edges_to_graphml([], [])
    assert isinstance(doc, GraphMLDoc)
    assert "<graphml" in doc.xml
    assert '<graph edgedefault="directed">' in doc.xml
    assert "<node" not in doc.xml
    assert doc.keys == ()


def test_single_node_emits_exactly_one_node_element() -> None:
    """(2) one node id='m1' -> exactly one '<node id="m1">'."""
    xml = graphml_document([{"id": "m1", "type": "Material", "name": "steel"}], [])
    assert xml.count('<node id="m1">') == 1


def test_str_prop_yields_string_key_and_matching_data() -> None:
    """(3) a str prop 'name' -> a <key attr.type="string"> and a matching <data>."""
    node = {"id": "n1", "properties": {"name": "steel"}}
    doc = nodes_edges_to_graphml([node], [])
    (key,) = doc.keys
    assert key.for_ == "node"
    assert key.attr_name == "name"
    assert key.attr_type == "string"
    assert f'<key id="{key.id}" for="node" attr.name="name" attr.type="string"/>' in doc.xml
    assert f'<data key="{key.id}">steel</data>' in doc.xml


def test_int_prop_is_long_and_float_prop_is_double() -> None:
    """(4) an int prop -> attr.type="long"; a float prop -> attr.type="double"."""
    node = {"id": "n1", "properties": {"count": 3, "score": 1.5}}
    doc = nodes_edges_to_graphml([node], [])
    by_name = {k.attr_name: k for k in doc.keys}
    assert by_name["count"].attr_type == "long"
    assert by_name["score"].attr_type == "double"
    assert 'attr.name="count" attr.type="long"' in doc.xml
    assert 'attr.name="score" attr.type="double"' in doc.xml
    assert f'<data key="{by_name["count"].id}">3</data>' in doc.xml
    assert f'<data key="{by_name["score"].id}">1.5</data>' in doc.xml


def test_edge_emits_source_target_element() -> None:
    """(5) an edge s->t -> '<edge source="s" target="t">'."""
    xml = graphml_document(
        [{"id": "s"}, {"id": "t"}],
        [{"source": "s", "target": "t", "type": "REL"}],
    )
    assert '<edge source="s" target="t">' in xml


def test_ampersand_in_name_is_escaped() -> None:
    """(6) a name value with '&' is escaped to '&amp;'."""
    node = {"id": "n1", "properties": {"name": "A & B"}}
    xml = graphml_document([node], [])
    assert "A &amp; B" in xml
    assert "A & B" not in xml


def test_directed_false_sets_undirected_edgedefault() -> None:
    """(7) directed=False -> edgedefault="undirected"."""
    doc = nodes_edges_to_graphml([], [], directed=False)
    assert '<graph edgedefault="undirected">' in doc.xml
    assert '<graph edgedefault="directed">' not in doc.xml


def test_collect_keys_is_deterministic() -> None:
    """(8) collect_keys is deterministic: same list on a repeat call."""
    nodes = [
        {"id": "a", "properties": {"name": "x", "count": 1}},
        {"id": "b", "properties": {"count": 2, "flag": True}},
    ]
    edges = [{"source": "a", "target": "b", "properties": {"weight": 0.5}}]
    first = collect_keys(nodes, edges)
    second = collect_keys(nodes, edges)
    assert first == second
    # First-seen order across nodes then edges, with inferred types.
    assert [(k.attr_name, k.for_, k.attr_type) for k in first] == [
        ("name", "node", "string"),
        ("count", "node", "long"),
        ("flag", "node", "boolean"),
        ("weight", "edge", "double"),
    ]


def test_bool_prop_renders_lowercase_and_boolean_type() -> None:
    """A bool prop is typed 'boolean' and rendered as lower-case true/false."""
    node = {"id": "n1", "properties": {"active": True}}
    doc = nodes_edges_to_graphml([node], [])
    (key,) = doc.keys
    assert key.attr_type == "boolean"
    assert f'<data key="{key.id}">true</data>' in doc.xml


def test_graphmlkey_and_doc_as_dict_round_trip() -> None:
    """GraphMLKey.as_dict / GraphMLDoc.as_dict expose plain-dict views."""
    key = GraphMLKey(id="d0", for_="node", attr_name="name", attr_type="string")
    assert key.as_dict() == {
        "id": "d0",
        "for": "node",
        "attr_name": "name",
        "attr_type": "string",
    }
    doc = nodes_edges_to_graphml([{"id": "n1", "properties": {"name": "x"}}], [])
    as_dict = doc.as_dict()
    assert as_dict["xml"] == doc.xml
    assert as_dict["keys"] == [k.as_dict() for k in doc.keys]


def test_node_and_edge_keys_have_distinct_id_prefixes() -> None:
    """Node keys are prefixed 'd', edge keys 'e' — no id collision across scopes."""
    nodes = [{"id": "a", "properties": {"name": "x"}}]
    edges = [{"source": "a", "target": "a", "properties": {"weight": 1.0}}]
    doc = nodes_edges_to_graphml(nodes, edges)
    ids = [k.id for k in doc.keys]
    assert ids == ["d0", "e0"]

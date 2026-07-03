"""§22.6 — tests for the JSON-LD graph serializer (RU: тесты сериализатора)."""

from __future__ import annotations

import json

from kg_retrievers.graph_jsonld_serializer import (
    DEFAULT_CONTEXT,
    JsonLdGraph,
    attach_edges,
    node_object,
    to_json,
    to_jsonld,
)


def test_empty_document() -> None:
    # (1) empty in -> context + empty graph.
    doc = to_jsonld([], []).as_dict()
    assert doc == {"@context": DEFAULT_CONTEXT, "@graph": []}


def test_default_context_has_vocab_and_kg() -> None:
    assert "@vocab" in DEFAULT_CONTEXT
    assert "kg" in DEFAULT_CONTEXT


def test_node_object_id_type_and_name() -> None:
    # (2) id/label/name map to @id/@type/name.
    obj = node_object({"id": "m1", "label": "Material", "name": "Al"})
    assert obj["@id"] == "kg:m1"
    assert obj["@type"] == "Material"
    assert obj["name"] == "Al"


def test_node_object_carries_arbitrary_prop() -> None:
    # (3) a plain property is copied through onto the object.
    obj = node_object({"id": "m1", "label": "Material", "hardness": 5})
    assert obj["hardness"] == 5


def test_edge_folds_into_subject() -> None:
    # (4) an edge becomes a predicate key with a reference value on the subject.
    nodes = [
        {"id": "s", "label": "Material", "name": "Al"},
        {"id": "t", "label": "Property", "name": "hardness"},
    ]
    edges = [{"source": "s", "target": "t", "type": "HAS_PROPERTY"}]
    doc = to_jsonld(nodes, edges).as_dict()
    subject = next(o for o in doc["@graph"] if o["@id"] == "kg:s")
    assert subject["HAS_PROPERTY"] == {"@id": "kg:t"}


def test_two_same_type_edges_collapse_to_list() -> None:
    # (5) two edges of the same predicate from one subject -> a list.
    nodes = [
        {"id": "s", "label": "Material"},
        {"id": "a", "label": "Property"},
        {"id": "b", "label": "Property"},
    ]
    edges = [
        {"source": "s", "target": "a", "type": "HAS_PROPERTY"},
        {"source": "s", "target": "b", "type": "HAS_PROPERTY"},
    ]
    doc = to_jsonld(nodes, edges).as_dict()
    subject = next(o for o in doc["@graph"] if o["@id"] == "kg:s")
    assert subject["HAS_PROPERTY"] == [{"@id": "kg:a"}, {"@id": "kg:b"}]


def test_custom_context_overrides_default() -> None:
    # (6) a caller-supplied context replaces the default verbatim.
    custom = {"@vocab": "https://example.org/v#", "kg": "https://example.org/id/"}
    doc = to_jsonld([{"id": "m1", "label": "Material"}], [], context=custom).as_dict()
    assert doc["@context"] == custom
    assert doc["@context"] != DEFAULT_CONTEXT


def test_to_json_round_trips() -> None:
    # (7) to_json parses back to the same dict as as_dict.
    nodes = [{"id": "m1", "label": "Material", "name": "Al", "hardness": 5}]
    edges = [{"source": "m1", "target": "m1", "type": "SELF"}]
    text = to_json(nodes, edges)
    assert json.loads(text) == to_jsonld(nodes, edges).as_dict()


def test_graph_length_equals_unique_nodes() -> None:
    # (8) duplicate ids collapse; @graph length == unique node count.
    nodes = [
        {"id": "m1", "label": "Material"},
        {"id": "m1", "label": "Material"},  # duplicate id
        {"id": "m2", "label": "Material"},
    ]
    doc = to_jsonld(nodes, []).as_dict()
    assert len(doc["@graph"]) == 2


def test_attach_edges_mutates_in_place() -> None:
    objs = {"s": {"@id": "kg:s", "@type": "Material"}}
    attach_edges(objs, [{"source": "s", "target": "t", "type": "REL"}])
    assert objs["s"]["REL"] == {"@id": "kg:t"}


def test_attach_edges_ignores_unknown_subject() -> None:
    objs: dict[str, dict[str, object]] = {"s": {"@id": "kg:s"}}
    attach_edges(objs, [{"source": "ghost", "target": "t", "type": "REL"}])
    assert "REL" not in objs["s"]


def test_jsonldgraph_is_frozen_with_tuple_graph() -> None:
    g = JsonLdGraph(context=DEFAULT_CONTEXT, graph=({"@id": "kg:m1"},))
    assert isinstance(g.graph, tuple)
    assert g.as_dict()["@graph"] == [{"@id": "kg:m1"}]

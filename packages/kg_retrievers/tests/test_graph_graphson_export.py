"""Tests for GraphSON v3 line-delimited export (§22.6).

Hand-checkable: build small node/edge dicts, then assert the exact GraphSON v3 shape and
the line-delimited framing. RU/EN — комментарии по-русски, код по-английски.
"""

from __future__ import annotations

import json

from kg_retrievers.graph_graphson_export import (
    GraphsonVertex,
    to_graphson,
    vertex_object,
)


def test_no_edge_node_properties_exclude_id_and_label() -> None:
    """(1) node without edges → properties hold only non-reserved keys, wrapped."""
    node = {"id": "a", "label": "Material", "name": "Al"}
    vertex = vertex_object(node, {})
    assert vertex.as_dict()["properties"] == {"name": [{"value": "Al"}]}


def test_label_taken_from_label_key() -> None:
    """(2) as_dict()['label'] echoes the node's label field."""
    node = {"id": "a", "label": "Material", "name": "Al"}
    assert vertex_object(node, {}).as_dict()["label"] == "Material"


def test_out_edge_target_lands_in_inV() -> None:
    """(3) edge a-[USES]->b → outE['USES'][0]['inV'] == 'b'."""
    node = {"id": "a", "label": "Material"}
    edges_by_source = {"a": [{"source": "a", "type": "USES", "target": "b"}]}
    vertex = vertex_object(node, edges_by_source)
    assert vertex.as_dict()["outE"]["USES"][0]["inV"] == "b"


def test_two_edges_same_rel_one_list_length_two() -> None:
    """(4) two out-edges of the same rel type accumulate in one list of length 2."""
    node = {"id": "a", "label": "Material"}
    edges_by_source = {
        "a": [
            {"source": "a", "type": "USES", "target": "b"},
            {"source": "a", "type": "USES", "target": "c"},
        ]
    }
    out_e = vertex_object(node, edges_by_source).as_dict()["outE"]
    assert len(out_e["USES"]) == 2
    assert [e["inV"] for e in out_e["USES"]] == ["b", "c"]


def test_to_graphson_emits_one_line_per_node() -> None:
    """(5) to_graphson yields exactly len(nodes) newline-terminated json-dict lines."""
    nodes = [
        {"id": "a", "label": "Material", "name": "Al"},
        {"id": "b", "label": "Process"},
    ]
    edges = [{"source": "a", "type": "USES", "target": "b"}]
    text = to_graphson(nodes, edges)
    lines = text.splitlines()
    assert len(lines) == len(nodes)
    assert text.endswith("\n")
    for line in lines:
        assert isinstance(json.loads(line), dict)


def test_first_line_has_id_key() -> None:
    """(6) json.loads of the first emitted line exposes an 'id' key."""
    nodes = [{"id": "a", "label": "Material"}]
    first = to_graphson(nodes, []).splitlines()[0]
    assert "id" in json.loads(first)


def test_empty_nodes_yield_empty_string() -> None:
    """(7) no nodes → empty output string."""
    assert to_graphson([], [{"source": "a", "type": "USES", "target": "b"}]) == ""


def test_two_distinct_rel_types_yield_two_outE_keys() -> None:
    """(8) a node with two distinct rel types produces two keys under outE."""
    node = {"id": "a", "label": "Material"}
    edges_by_source = {
        "a": [
            {"source": "a", "type": "USES", "target": "b"},
            {"source": "a", "type": "MADE_OF", "target": "c"},
        ]
    }
    out_e = vertex_object(node, edges_by_source).as_dict()["outE"]
    assert set(out_e) == {"USES", "MADE_OF"}


def test_edge_id_is_deterministic() -> None:
    """Synthesized edge id follows the '<id>-<rel>-<target>' contract (hand-checkable)."""
    node = {"id": "a", "label": "Material"}
    edges_by_source = {"a": [{"source": "a", "type": "USES", "target": "b"}]}
    edge = vertex_object(node, edges_by_source).as_dict()["outE"]["USES"][0]
    assert edge["id"] == "a-USES-b"


def test_graphson_vertex_is_frozen() -> None:
    """GraphsonVertex is an immutable frozen dataclass."""
    vertex = GraphsonVertex(id="a", label="Material", out_edges=(), properties=())
    try:
        vertex.id = "b"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("GraphsonVertex should be frozen")

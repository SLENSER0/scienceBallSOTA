"""Hand-checked GML export over tiny node/edge dicts (§22.6).

Every assertion is verifiable by eye — no graph store, just dicts in and GML
text out. RU: ручная проверка сериализации в GML.
"""

from __future__ import annotations

from kg_retrievers.graph_gml_export import GmlGraph, _escape_gml, to_gml

# A minimal two-node, one-edge graph: Al --USES--> XRD.
NODES = [
    {"id": "m1", "name": "Al", "type": "Material"},
    {"id": "d1", "name": "XRD", "type": "Method"},
]
EDGES = [{"source": "m1", "target": "d1", "type": "USES"}]


def test_wrapper_start_and_end() -> None:
    # (1) output opens with 'graph [' and ends with a closed brace + newline.
    out = to_gml(NODES, EDGES)
    assert out.startswith("graph [")
    assert out.endswith("]\n")


def test_directed_flag_true() -> None:
    # (2) directed=True (default) emits 'directed 1'.
    out = to_gml(NODES, EDGES)
    assert "directed 1" in out


def test_first_node_block() -> None:
    # (3) first node gets int id 0 and label drawn from its name.
    out = to_gml(NODES, EDGES)
    node_block = out.split("node [")[1].split("]")[0]
    assert "id 0" in node_block
    assert 'label "Al"' in node_block


def test_edge_source_target_ints() -> None:
    # (4) edge m1->d1 resolves to 'source 0' and 'target 1' inside an edge block.
    out = to_gml(NODES, EDGES)
    edge_block = out.split("edge [")[1].split("]")[0]
    assert "source 0" in edge_block
    assert "target 1" in edge_block


def test_edge_label_rel_type() -> None:
    # (5) the edge label carries the relation type.
    out = to_gml(NODES, EDGES)
    assert 'label "USES"' in out


def test_quote_in_name_escaped() -> None:
    # (6) a double quote in a node name is doubled per GML string rules.
    nodes = [{"id": "n1", "name": 'the "hard" alloy'}]
    out = to_gml(nodes, [])
    assert 'label "the ""hard"" alloy"' in out
    assert _escape_gml('a"b') == 'a""b'


def test_directed_flag_false() -> None:
    # (7) directed=False emits 'directed 0'.
    out = to_gml(NODES, EDGES, directed=False)
    assert "directed 0" in out
    assert "directed 1" not in out


def test_block_counts_match() -> None:
    # (8) one node/edge block per input node/edge.
    nodes = [
        {"id": "a", "name": "A"},
        {"id": "b", "name": "B"},
        {"id": "c", "name": "C"},
    ]
    edges = [
        {"source": "a", "target": "b", "type": "R1"},
        {"source": "b", "target": "c", "type": "R2"},
    ]
    out = to_gml(nodes, edges)
    assert out.count("node [") == len(nodes)
    assert out.count("edge [") == len(edges)


def test_label_fallback_chain() -> None:
    # Name missing -> fall back to label, then type, then the id string.
    out = to_gml([{"id": "x", "type": "Material"}], [])
    assert 'label "Material"' in out
    out2 = to_gml([{"id": "z"}], [])
    assert 'label "z"' in out2


def test_rel_prefers_rel_key() -> None:
    # 'rel' takes precedence over 'type' for the edge label.
    out = to_gml(NODES, [{"source": "m1", "target": "d1", "rel": "MEASURED_BY"}])
    assert 'label "MEASURED_BY"' in out


def test_gmlgraph_as_dict() -> None:
    # The frozen model round-trips through as_dict as plain lists.
    graph = GmlGraph(
        directed=1,
        nodes=((0, "m1", "Al"),),
        edges=((0, 0, "SELF"),),
    )
    assert graph.as_dict() == {
        "directed": 1,
        "nodes": [[0, "m1", "Al"]],
        "edges": [[0, 0, "SELF"]],
    }


def test_empty_graph() -> None:
    # No nodes / edges -> still a valid wrapper with the directed flag.
    out = to_gml([], [])
    assert out.startswith("graph [")
    assert out.endswith("]\n")
    assert "directed 1" in out
    assert out.count("node [") == 0
    assert out.count("edge [") == 0

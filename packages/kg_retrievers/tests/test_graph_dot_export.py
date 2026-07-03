"""Hand-checked DOT export over tiny node/edge dicts (§22.6).

Every assertion is verifiable by eye — no graph store, just dicts in and DOT
text out. RU: ручная проверка сериализации в Graphviz DOT.
"""

from __future__ import annotations

from kg_retrievers.graph_dot_export import (
    DotGraph,
    _quote,
    edge_line,
    node_line,
    render,
    to_dot,
)


def test_empty_render_header() -> None:
    # (1) empty graph -> valid wrapper with default rankdir=LR.
    dg = to_dot([], [])
    out = render(dg)
    assert out.startswith("digraph kg {")
    assert "rankdir=LR" in out
    assert out.endswith("}")  # (8)
    assert dg.node_count == 0
    assert dg.edge_count == 0


def test_node_line_label() -> None:
    # (2) id=m1 name=Al -> label reads "Al".
    line = node_line({"id": "m1", "name": "Al"})
    assert line == '"m1" [label="Al"];'


def test_material_gets_fillcolor() -> None:
    # (3) a Material node is filled with its per-type colour.
    line = node_line({"id": "m1", "name": "Al", "type": "Material"})
    assert "style=filled" in line
    assert "fillcolor=" in line
    assert 'label="Al"' in line


def test_unknown_type_unfilled() -> None:
    line = node_line({"id": "x1", "name": "thing", "type": "Nope"})
    assert "style=filled" not in line
    assert "fillcolor" not in line


def test_edge_line_rel_label() -> None:
    # (4) s -> t of type HAS_PROPERTY.
    line = edge_line({"source": "s", "target": "t", "type": "HAS_PROPERTY"})
    assert '"s" -> "t"' in line
    assert 'label="HAS_PROPERTY"' in line


def test_edge_line_src_tgt_aliases() -> None:
    line = edge_line({"src": "a", "tgt": "b", "rel": "MENTIONS"})
    assert '"a" -> "b"' in line
    assert 'label="MENTIONS"' in line


def test_edge_line_no_type() -> None:
    line = edge_line({"source": "a", "target": "b"})
    assert line == '"a" -> "b";'


def test_quote_escapes_quote() -> None:
    # (5) an embedded double-quote is escaped.
    assert _quote('say "hi"') == 'say \\"hi\\"'
    line = node_line({"id": "n1", "name": 'TiO2 "rutile"'})
    assert '\\"rutile\\"' in line
    # DOT-quoting stays balanced: only escaped inner quotes, no raw ones.
    inner = line.split("label=", 1)[1]
    assert inner.count('\\"') == 2


def test_quote_escapes_newline() -> None:
    assert _quote("a\nb") == "a\\nb"
    assert _quote("a\r\nb") == "a\\nb"


def test_label_falls_back_to_type_then_id() -> None:
    assert 'label="Material"' in node_line({"id": "m1", "type": "Material"})
    # no name, no known type -> falls back to id.
    line = node_line({"id": "solo"})
    assert 'label="solo"' in line


def test_counts_match_input() -> None:
    # (6) node_count / edge_count mirror the input lengths.
    nodes = [
        {"id": "m1", "name": "Al", "type": "Material"},
        {"id": "p1", "name": "recovery", "type": "Property"},
        {"id": "x1", "name": "loose"},
    ]
    edges = [
        {"source": "m1", "target": "p1", "type": "HAS_PROPERTY"},
        {"source": "x1", "target": "m1", "type": "REL"},
    ]
    dg = to_dot(nodes, edges)
    assert dg.node_count == 3
    assert dg.edge_count == 2
    out = render(dg)
    assert out.count(" -> ") == 2


def test_rankdir_override_tb() -> None:
    # (7) rankdir override to TB appears in the output.
    dg = to_dot([{"id": "a", "name": "A"}], [], rankdir="TB")
    out = render(dg)
    assert "rankdir=TB" in out
    assert "rankdir=LR" not in out


def test_custom_name_in_wrapper() -> None:
    dg = to_dot([], [], name="sub")
    out = render(dg)
    assert out.startswith("digraph sub {")


def test_dotgraph_as_dict_roundtrips() -> None:
    dg = to_dot([{"id": "a", "name": "A"}], [{"source": "a", "target": "a", "type": "R"}])
    d = dg.as_dict()
    assert d == {
        "name": "kg",
        "body": dg.body,
        "node_count": 1,
        "edge_count": 1,
    }
    assert isinstance(dg, DotGraph)


def test_full_render_is_wellformed() -> None:
    nodes = [
        {"id": "m1", "name": "Al", "type": "Material"},
        {"id": "p1", "name": "recovery", "type": "Property"},
    ]
    edges = [{"source": "m1", "target": "p1", "type": "HAS_PROPERTY"}]
    out = render(to_dot(nodes, edges))
    assert out.startswith("digraph kg {")
    assert out.endswith("}")
    assert 'label="HAS_PROPERTY"' in out
    assert "style=filled" in out
    # one line per node + edge + rankdir, all indented.
    body_lines = out.splitlines()[1:-1]
    assert all(ln.startswith("  ") for ln in body_lines)
    assert len(body_lines) == 4  # rankdir + 2 nodes + 1 edge

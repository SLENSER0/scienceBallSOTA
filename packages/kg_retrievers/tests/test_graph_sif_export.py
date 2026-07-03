"""Tests for SIF (Simple Interaction Format) export (§22.6).

Hand-checkable assertions over :mod:`kg_retrievers.graph_sif_export`.
"""

from __future__ import annotations

from kg_retrievers.graph_sif_export import SifLine, group_edges, to_sif


def _edge(source: str, relation: str, target: str) -> dict:
    return {"source": source, "relation": relation, "target": target}


def test_single_edge_renders_source_tab_relation_tab_target() -> None:
    # (1) one edge a-[r]->b renders 'a\tr\tb'.
    assert to_sif([_edge("a", "r", "b")]) == "a\tr\tb"


def test_two_edges_same_source_relation_collapse_to_one_line() -> None:
    # (2) a-[r]->b and a-[r]->c collapse to one SifLine ('b','c') -> 'a\tr\tb\tc'.
    lines = group_edges([_edge("a", "r", "b"), _edge("a", "r", "c")])
    assert len(lines) == 1
    assert lines[0] == SifLine(source="a", relation="r", targets=("b", "c"))
    assert lines[0].render() == "a\tr\tb\tc"
    assert to_sif([_edge("a", "r", "b"), _edge("a", "r", "c")]) == "a\tr\tb\tc"


def test_different_relations_produce_two_lines() -> None:
    # (3) a-[r]->b and a-[s]->b produce two separate lines.
    lines = group_edges([_edge("a", "r", "b"), _edge("a", "s", "b")])
    assert len(lines) == 2
    assert lines[0] == SifLine("a", "r", ("b",))
    assert lines[1] == SifLine("a", "s", ("b",))
    assert to_sif([_edge("a", "r", "b"), _edge("a", "s", "b")]) == "a\tr\tb\na\ts\tb"


def test_group_edges_preserves_first_seen_key_ordering() -> None:
    # (4) first-seen key order: (b,r) seen before (a,r) despite interleaving.
    edges = [
        _edge("b", "r", "x"),
        _edge("a", "r", "y"),
        _edge("b", "r", "z"),  # updates the already-seen (b,r) group
    ]
    lines = group_edges(edges)
    assert [(line.source, line.relation) for line in lines] == [("b", "r"), ("a", "r")]
    assert lines[0].targets == ("x", "z")
    assert lines[1].targets == ("y",)


def test_as_dict_targets_is_a_list() -> None:
    # (5) SifLine.as_dict()['targets'] == ['b','c'] (list, not tuple).
    line = SifLine(source="a", relation="r", targets=("b", "c"))
    d = line.as_dict()
    assert d == {"source": "a", "relation": "r", "targets": ["b", "c"]}
    assert isinstance(d["targets"], list)


def test_self_loop_renders_source_relation_source() -> None:
    # (6) a self-loop a-[r]->a renders 'a\tr\ta'.
    assert to_sif([_edge("a", "r", "a")]) == "a\tr\ta"


def test_empty_edges_render_empty_string() -> None:
    # (7) empty edges -> ''.
    assert group_edges([]) == []
    assert to_sif([]) == ""


def test_to_sif_joins_lines_without_trailing_blank() -> None:
    # (8) lines joined with '\n', no trailing blank line beyond the last.
    out = to_sif([_edge("a", "r", "b"), _edge("c", "s", "d")])
    assert out == "a\tr\tb\nc\ts\td"
    assert not out.endswith("\n")
    assert out.count("\n") == 1  # two lines -> exactly one separator

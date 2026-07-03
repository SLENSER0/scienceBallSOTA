"""Tests for the Mermaid graph-diagram export (§22.6).

Hand-checks the pure-python serializer: id sanitizing, label quoting, node/edge
declarations, the empty diagram, direction header, the body line count and the fenced
Markdown wrapper. No store needed — the input is plain node/edge dicts.
"""

from __future__ import annotations

from kg_retrievers.graph_mermaid_export import (
    MermaidDiagram,
    _label,
    _safe_id,
    edge_decl,
    fenced,
    node_decl,
    to_mermaid,
)


def test_empty_diagram_is_bare_header() -> None:
    """(1) No nodes/edges → text is exactly the ``graph LR`` header, no body."""
    diagram = to_mermaid([], [])
    assert diagram.text == "graph LR"
    assert diagram.lines == ()
    assert diagram.direction == "LR"


def test_node_decl_sanitizes_id_and_quotes_label() -> None:
    """(2) id ``m-1`` name ``Al 6061`` → ``m_1["Al 6061"]``."""
    node = {"id": "m-1", "name": "Al 6061"}
    assert node_decl(node) == 'm_1["Al 6061"]'


def test_direction_tb_sets_header() -> None:
    """(3) direction=TB → first line ``graph TB``."""
    diagram = to_mermaid([{"id": "a", "name": "A"}], [], direction="TB")
    assert diagram.direction == "TB"
    assert diagram.text.splitlines()[0] == "graph TB"


def test_edge_decl_with_type() -> None:
    """(4) edge s→t type HAS → ``s -->|HAS| t`` with sanitized ids."""
    edge = {"source": "s", "target": "t", "type": "HAS"}
    assert edge_decl(edge) == "s -->|HAS| t"


def test_edge_decl_sanitizes_endpoint_ids() -> None:
    """(4b) endpoint ids are run through ``_safe_id`` before the arrow."""
    edge = {"source": "n-1", "target": "n 2", "type": "USES"}
    assert edge_decl(edge) == "n_1 -->|USES| n_2"


def test_edge_decl_without_type_has_no_pipe() -> None:
    """(5) edge with no type → bare ``s --> t`` (no pipe label)."""
    assert edge_decl({"source": "s", "target": "t"}) == "s --> t"
    assert edge_decl({"source": "s", "target": "t", "type": ""}) == "s --> t"


def test_label_with_quote_is_made_safe() -> None:
    """(6) a ``"`` in a label is replaced with ``#quot;`` — no raw quote leaks out."""
    node = {"id": "x", "name": 'the "big" one'}
    label = _label(node)
    assert '"' not in label
    assert "#quot;" in label
    decl = node_decl(node)
    # The only literal quotes in the declaration are the two wrapping the label.
    assert decl.count('"') == 2
    assert decl == 'x["the #quot;big#quot; one"]'


def test_fenced_wraps_in_mermaid_block() -> None:
    """(7) fenced() starts with ```mermaid and ends with the closing fence."""
    diagram = to_mermaid([{"id": "a", "name": "A"}], [])
    block = fenced(diagram)
    assert block.startswith("```mermaid")
    assert block.endswith("```")
    assert diagram.text in block


def test_line_count_excludes_header() -> None:
    """(8) body line count == #nodes + #edges (the header is not in ``lines``)."""
    nodes = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}, {"id": "c"}]
    edges = [
        {"source": "a", "target": "b", "type": "REL"},
        {"source": "b", "target": "c"},
    ]
    diagram = to_mermaid(nodes, edges)
    assert len(diagram.lines) == len(nodes) + len(edges)
    # The header lives in text but not in lines.
    assert "graph LR" not in diagram.lines
    assert diagram.text.splitlines()[0] == "graph LR"
    assert diagram.text.splitlines()[1:] == list(diagram.lines)


def test_safe_id_fallbacks() -> None:
    """``_safe_id`` trims edge underscores and never returns blank."""
    assert _safe_id("m-1") == "m_1"
    assert _safe_id("(a)") == "a"
    assert _safe_id("!!!") == "_"
    assert _safe_id("") == "_"


def test_label_prefers_name_then_type_then_id() -> None:
    """``_label`` falls back name → type → id → ''."""
    assert _label({"id": "x", "name": "N", "type": "T"}) == "N"
    assert _label({"id": "x", "type": "T"}) == "T"
    assert _label({"id": "x"}) == "x"
    assert _label({}) == ""


def test_diagram_as_dict_roundtrips_fields() -> None:
    """``MermaidDiagram.as_dict`` exposes direction / lines / text."""
    diagram = to_mermaid([{"id": "a", "name": "A"}], [])
    d = diagram.as_dict()
    assert d == {"direction": "LR", "lines": list(diagram.lines), "text": diagram.text}
    assert isinstance(d["lines"], list)


def test_frozen_dataclass_is_immutable() -> None:
    """The dataclass is frozen — attribute assignment raises."""
    diagram = MermaidDiagram(direction="LR", lines=(), text="graph LR")
    try:
        diagram.direction = "TB"  # type: ignore[misc]
    except Exception as exc:
        assert exc.__class__.__name__ == "FrozenInstanceError"
    else:  # pragma: no cover
        raise AssertionError("expected FrozenInstanceError")


def test_full_diagram_text_layout() -> None:
    """End-to-end: a small graph renders a hand-checkable Mermaid document."""
    nodes = [{"id": "m-1", "name": "Al 6061"}, {"id": "p-1", "name": "hardness"}]
    edges = [{"source": "m-1", "target": "p-1", "type": "HAS_PROPERTY"}]
    diagram = to_mermaid(nodes, edges, direction="LR")
    assert diagram.text == ('graph LR\nm_1["Al 6061"]\np_1["hardness"]\nm_1 -->|HAS_PROPERTY| p_1')

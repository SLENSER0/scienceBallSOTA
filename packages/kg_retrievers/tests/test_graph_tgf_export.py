"""Tests for TGF export (§22) — hand-checkable string/shape assertions."""

from __future__ import annotations

from kg_retrievers.graph_tgf_export import TgfDoc, build_tgf, to_tgf


def test_single_node_line() -> None:
    """A single node ``{id:'n1', name:'Al'}`` renders the line ``n1 Al``."""
    doc = build_tgf([{"id": "n1", "name": "Al"}], [])
    out = to_tgf(doc)
    assert out.splitlines()[0] == "n1 Al"


def test_separator_is_exactly_hash_and_appears_once() -> None:
    """The separator line equals ``#`` exactly and appears exactly once."""
    doc = build_tgf(
        [{"id": "a", "name": "A"}],
        [{"source": "a", "target": "a", "type": "SELF"}],
    )
    out = to_tgf(doc)
    lines = out.splitlines()
    assert lines.count("#") == 1
    assert "#" in lines
    # It sits between the node block and the edge block.
    sep_index = lines.index("#")
    assert lines[sep_index] == "#"
    assert lines[:sep_index] == ["a A"]
    assert lines[sep_index + 1 :] == ["a a SELF"]


def test_edge_with_type_label() -> None:
    """Edge ``{source:'a', target:'b', type:'HAS'}`` renders ``a b HAS``."""
    doc = build_tgf(
        [{"id": "a"}, {"id": "b"}],
        [{"source": "a", "target": "b", "type": "HAS"}],
    )
    out = to_tgf(doc)
    assert out.splitlines()[-1] == "a b HAS"


def test_edge_without_type_has_no_trailing_whitespace() -> None:
    """Edge with no ``type`` renders ``a b`` with no trailing whitespace."""
    doc = build_tgf(
        [{"id": "a"}, {"id": "b"}],
        [{"source": "a", "target": "b"}],
    )
    edge_line = to_tgf(doc).splitlines()[-1]
    assert edge_line == "a b"
    assert edge_line == edge_line.rstrip()


def test_node_missing_name_uses_id_as_label() -> None:
    """A node missing ``name`` uses its id as the label."""
    doc = build_tgf([{"id": "x9"}], [])
    assert doc.nodes == (("x9", "x9"),)
    assert to_tgf(doc).splitlines()[0] == "x9 x9"


def test_empty_name_falls_back_to_id() -> None:
    """An empty (falsy) ``name`` falls back to the id label."""
    doc = build_tgf([{"id": "x9", "name": ""}], [])
    assert doc.nodes == (("x9", "x9"),)


def test_newline_in_label_flattened() -> None:
    """A label containing ``\\n`` is flattened to a single line."""
    doc = build_tgf([{"id": "n1", "name": "line1\nline2"}], [])
    out = to_tgf(doc)
    assert out == "n1 line1 line2\n#"
    # No embedded newline inside the node's label region.
    assert out.splitlines()[0] == "n1 line1 line2"


def test_crlf_in_label_flattened_single_space() -> None:
    """A ``\\r\\n`` in a label collapses to a single space, not two."""
    doc = build_tgf([{"id": "n1", "name": "a\r\nb"}], [])
    assert to_tgf(doc).splitlines()[0] == "n1 a b"


def test_empty_graph_is_just_hash() -> None:
    """An empty graph renders as exactly ``#``."""
    doc = build_tgf([], [])
    assert to_tgf(doc) == "#"


def test_as_dict_edges_are_three_tuples() -> None:
    """``as_dict()['edges']`` is a list of 3-tuples; nodes are 2-tuples."""
    doc = build_tgf(
        [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
        [{"source": "a", "target": "b", "type": "HAS"}],
    )
    d = doc.as_dict()
    assert d["edges"] == [("a", "b", "HAS")]
    assert all(isinstance(e, tuple) and len(e) == 3 for e in d["edges"])
    assert d["nodes"] == [("a", "A"), ("b", "B")]
    assert all(isinstance(n, tuple) and len(n) == 2 for n in d["nodes"])


def test_tgfdoc_is_frozen() -> None:
    """:class:`TgfDoc` is an immutable (frozen) value."""
    doc = TgfDoc(nodes=(("a", "A"),), edges=())
    try:
        doc.nodes = ()  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject assignment
        raise AssertionError("TgfDoc should be frozen")


def test_full_document_roundtrip_shape() -> None:
    """A small graph renders in node-block / ``#`` / edge-block order."""
    doc = build_tgf(
        [{"id": "1", "name": "Al"}, {"id": "2", "name": "O"}],
        [
            {"source": "1", "target": "2", "type": "BONDS"},
            {"source": "2", "target": "1"},
        ],
    )
    out = to_tgf(doc)
    assert out == "1 Al\n2 O\n#\n1 2 BONDS\n2 1"


def test_non_string_ids_stringified() -> None:
    """Integer ids / endpoints are stringified in the output."""
    doc = build_tgf(
        [{"id": 1, "name": "Al"}],
        [{"source": 1, "target": 1, "type": "SELF"}],
    )
    assert doc.nodes == (("1", "Al"),)
    assert doc.edges == (("1", "1", "SELF"),)

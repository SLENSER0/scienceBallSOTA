"""Tests for RDF N-Quads named-graph export (§22.6)."""

from __future__ import annotations

from kg_retrievers.graph_rdf_nquads import (
    DEFAULT_GRAPH,
    RdfQuad,
    edge_quad,
    graph_iri,
    to_nquads,
)


def test_edge_graph_from_source_doc() -> None:
    """(1) source_doc mints the named-graph IRI, which ends with the doc id."""
    edge = {"source": "a", "target": "b", "type": "USES", "source_doc": "doc1"}
    quad = edge_quad(edge)
    assert quad.graph.endswith("doc1")
    assert quad.graph == graph_iri("doc1")


def test_to_nquad_ends_with_dot() -> None:
    """(2) A rendered quad terminates with ``' .'``."""
    quad = edge_quad({"source": "a", "target": "b", "type": "USES", "source_doc": "d"})
    assert quad.to_nquad().endswith(" .")


def test_to_nquad_has_four_terms_before_dot() -> None:
    """(3) Four whitespace-separated terms precede the trailing dot."""
    line = edge_quad({"source": "a", "target": "b", "type": "USES", "source_doc": "d"}).to_nquad()
    assert line.endswith(" .")
    terms = line[: -len(" .")].split()
    assert len(terms) == 4


def test_all_terms_angle_wrapped() -> None:
    """(4) Subject, predicate, object and graph are all angle-wrapped IRIs."""
    line = edge_quad({"source": "a", "target": "b", "type": "USES", "source_doc": "d"}).to_nquad()
    subj, pred, obj, graph = line[: -len(" .")].split()
    for term in (subj, pred, obj, graph):
        assert term.startswith("<") and term.endswith(">"), term


def test_missing_source_doc_falls_back_to_default() -> None:
    """(5) With no source_doc/graph the quad lands in the default graph."""
    quad = edge_quad({"source": "a", "target": "b", "type": "USES"})
    assert quad.graph == DEFAULT_GRAPH
    custom = edge_quad({"source": "a", "target": "b", "type": "USES"}, default_graph="urn:x")
    assert custom.graph == "urn:x"


def test_to_nquads_one_line_per_edge() -> None:
    """(6) One newline-terminated line is emitted per edge."""
    edges = [
        {"source": "a", "target": "b", "type": "USES", "source_doc": "doc1"},
        {"source": "b", "target": "c", "type": "CITES", "source_doc": "doc2"},
    ]
    out = to_nquads(edges)
    lines = out.splitlines()
    assert len(lines) == 2
    assert out.endswith("\n")
    assert out.count("\n") == 2


def test_as_dict_is_literal_false_for_edge() -> None:
    """(7) An edge quad's object is an IRI, so ``is_literal`` is False."""
    quad = edge_quad({"source": "a", "target": "b", "type": "USES", "source_doc": "d"})
    d = quad.as_dict()
    assert d["is_literal"] is False
    assert set(d) == {"subject", "predicate", "object", "is_literal", "graph"}


def test_empty_edges_yield_empty_string() -> None:
    """(8) No edges -> empty document (no trailing newline)."""
    assert to_nquads([]) == ""


def test_graph_alias_field() -> None:
    """The ``graph`` field is honoured when ``source_doc`` is absent."""
    quad = edge_quad({"source": "a", "target": "b", "type": "USES", "graph": "gX"})
    assert quad.graph == graph_iri("gX")


def test_frozen_quad_is_immutable() -> None:
    """The dataclass is frozen — attributes cannot be reassigned."""
    quad = RdfQuad("s", "p", "o", False, "g")
    try:
        quad.subject = "other"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("RdfQuad should be frozen")

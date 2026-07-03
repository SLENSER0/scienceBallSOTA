"""Tests for RDF N-Triples / Turtle export (§22.6).

Hand-checkable assertions over the fixed §22.6 mapping: entity IRIs under the
base IRI, ``rdf:type`` for labels, ``rdfs:label`` string literals, edge predicate
IRIs, escaping, line counts and the Turtle ``@prefix`` header.
"""

from __future__ import annotations

from kg_retrievers.graph_rdf_ntriples import (
    RDF_TYPE_IRI,
    RDFS_LABEL_IRI,
    RdfTriple,
    all_triples,
    edge_triple,
    node_triples,
    to_ntriples,
    to_turtle,
)


def test_node_label_becomes_rdf_type_iri() -> None:
    """(1) id='m1' label='Material' -> rdf:type IRI object, line ends ' .'."""
    triples = node_triples({"id": "m1", "label": "Material"})
    type_triples = [t for t in triples if t.predicate == RDF_TYPE_IRI]
    assert len(type_triples) == 1
    t = type_triples[0]
    assert t.is_literal is False
    assert t.object_ == "https://science-ball.example/kg/ontology#Material"
    line = t.to_ntriple()
    assert line.endswith(" .")
    assert "<https://science-ball.example/kg/ontology#Material>" in line
    assert line == (
        "<https://science-ball.example/kg/m/m1> "
        "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type> "
        "<https://science-ball.example/kg/ontology#Material> ."
    )


def test_name_becomes_rdfs_label_string_literal() -> None:
    """(2) name 'Al' -> rdfs:label triple, object '"Al"', is_literal True."""
    triples = node_triples({"id": "m1", "label": "Material", "name": "Al"})
    label_triples = [t for t in triples if t.predicate == RDFS_LABEL_IRI]
    assert len(label_triples) == 1
    t = label_triples[0]
    assert t.is_literal is True
    assert t.object_ == "Al"
    assert t.to_ntriple().endswith('"Al" .')
    assert '"Al"' in t.to_ntriple()


def test_literal_with_quote_is_backslash_escaped() -> None:
    """(3) a string literal containing '"' is backslash-escaped in to_ntriple."""
    t = RdfTriple(
        subject="https://science-ball.example/kg/m/x",
        predicate=RDFS_LABEL_IRI,
        object_='say "hi"',
        is_literal=True,
    )
    line = t.to_ntriple()
    assert '\\"hi\\"' in line
    assert line.endswith('"say \\"hi\\"" .')


def test_backslash_in_literal_is_escaped() -> None:
    """A backslash in the literal body is itself doubled before quote escaping."""
    t = RdfTriple(subject="s", predicate="p", object_="a\\b", is_literal=True)
    # object body 'a\b' -> escaped 'a\\b' inside the quotes.
    assert t.to_ntriple() == '<s> <p> "a\\\\b" .'


def test_edge_triple_all_iris() -> None:
    """(4) edge s->t type HAS_PROPERTY -> the exact three-IRI N-Triple line."""
    t = edge_triple({"source": "s", "target": "t", "type": "HAS_PROPERTY"})
    assert t.is_literal is False
    assert t.to_ntriple() == (
        "<https://science-ball.example/kg/m/s> "
        "<https://science-ball.example/kg/ontology#HAS_PROPERTY> "
        "<https://science-ball.example/kg/m/t> ."
    )


def test_edge_triple_accepts_src_dst_aliases() -> None:
    """``src``/``dst`` aliases resolve to the same entity IRIs as source/target."""
    a = edge_triple({"src": "s", "dst": "t", "type": "REL"})
    b = edge_triple({"source": "s", "target": "t", "type": "REL"})
    assert a == b


def test_ntriples_line_count_equals_triple_count() -> None:
    """(5) to_ntriples line count == total number of triples."""
    nodes = [
        {"id": "m1", "label": "Material", "name": "Al"},
        {"id": "m2", "label": "Property"},
    ]
    edges = [{"source": "m1", "target": "m2", "type": "HAS_PROPERTY"}]
    total = len(all_triples(nodes, edges))
    assert total == 4  # 2 for m1 (type+label), 1 for m2 (type), 1 edge
    doc = to_ntriples(nodes, edges)
    lines = doc.splitlines()
    assert len(lines) == total
    assert all(line.endswith(" .") for line in lines)


def test_turtle_has_prefix_header() -> None:
    """(6) to_turtle contains '@prefix rdfs:' and '@prefix rdf:'."""
    doc = to_turtle([{"id": "m1", "label": "Material"}], [])
    assert "@prefix rdf: " in doc
    assert "@prefix rdfs: " in doc
    assert "<http://www.w3.org/1999/02/22-rdf-syntax-ns#>" in doc
    # Body statement follows the header.
    assert "<https://science-ball.example/kg/m/m1>" in doc


def test_turtle_empty_still_has_header() -> None:
    """Empty input still emits the Turtle @prefix header (no body)."""
    doc = to_turtle([], [])
    assert "@prefix rdf: " in doc
    assert "@prefix rdfs: " in doc
    # No entity statements in an empty graph.
    assert "/m/m" not in doc


def test_empty_input_ntriples_is_empty_string() -> None:
    """(7) empty input -> to_ntriples() == ''."""
    assert to_ntriples([], []) == ""


def test_iris_are_angle_bracket_wrapped() -> None:
    """(8) IRIs are angle-bracket wrapped in the rendered line."""
    line = edge_triple({"source": "a", "target": "b", "type": "R"}).to_ntriple()
    # subject, predicate, object all wrapped
    assert line.count("<") == 3
    assert line.count(">") == 3
    for part in line[:-2].split(" "):
        if part:
            assert part.startswith("<") and part.endswith(">")


def test_rdftriple_as_dict_key_order() -> None:
    """as_dict emits the fixed §22.6 key order."""
    t = RdfTriple(subject="s", predicate="p", object_="o", is_literal=True)
    assert list(t.as_dict().keys()) == ["subject", "predicate", "object", "is_literal"]
    assert t.as_dict()["object"] == "o"


def test_node_without_name_has_only_type_triple() -> None:
    """A node lacking a name yields just the rdf:type triple."""
    triples = node_triples({"id": "m9", "label": "Material"})
    assert len(triples) == 1
    assert triples[0].predicate == RDF_TYPE_IRI


def test_node_without_label_yields_no_type_triple() -> None:
    """A node lacking a label yields no rdf:type triple (only rdfs:label if named)."""
    triples = node_triples({"id": "m9", "name": "thing"})
    assert len(triples) == 1
    assert triples[0].predicate == RDFS_LABEL_IRI

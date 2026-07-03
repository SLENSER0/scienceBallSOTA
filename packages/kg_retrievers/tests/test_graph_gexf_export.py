"""Tests for GEXF 1.3 (Gephi) graph export (§22.6).

Hand-checks the pure-stdlib serializer on plain node/edge ``dict`` inputs (already read
from the graph — no store needed here): the GEXF header/version, an empty-but-present
``<nodes>`` block, node ``id``/``label`` mapping, GEXF type inference for props,
integer edge ids with source/target, edge counting, XML escaping and the deterministic
first-seen order of the declared attribute columns.
"""

from __future__ import annotations

from kg_retrievers.graph_gexf_export import (
    GexfDoc,
    declare_attributes,
    gexf_document,
    to_gexf,
)


def test_empty_document_has_gexf_header_and_empty_nodes() -> None:
    """(1) Empty graph → GEXF 1.3 header, and a present-but-empty ``<nodes>`` block."""
    doc = to_gexf([], [])
    assert isinstance(doc, GexfDoc)
    assert "<gexf" in doc.xml
    assert 'version="1.3"' in doc.xml
    assert "<nodes>" in doc.xml
    assert "</nodes>" in doc.xml
    # Nothing between the open/close tags: the block is present but empty.
    between = doc.xml.split("<nodes>", 1)[1].split("</nodes>", 1)[0]
    assert between.strip() == ""
    assert doc.attr_columns == ()


def test_node_id_and_label_from_name() -> None:
    """(2) Node id='m1' with name='Al' → ``<node id="m1" label="Al"`` in the XML."""
    xml = gexf_document([{"id": "m1", "name": "Al"}], [])
    assert '<node id="m1" label="Al"' in xml


def test_declare_attributes_double_type() -> None:
    """(3) A float prop hardness=5.0 → ('hardness', 'double') in the column list."""
    cols = declare_attributes([{"id": "m1", "name": "Al", "hardness": 5.0}])
    assert ("hardness", "double") in cols


def test_declare_attributes_boolean_type() -> None:
    """(4) A bool prop → GEXF type 'boolean' (bool checked before int)."""
    cols = declare_attributes([{"id": "m1", "name": "Al", "verified": True}])
    assert ("verified", "boolean") in cols
    # And the attvalue renders as GEXF's true/false, not Python's True/False.
    doc = to_gexf([{"id": "m1", "name": "Al", "verified": True}], [])
    assert 'value="true"' in doc.xml


def test_declare_attributes_integer_and_string_types() -> None:
    """int → integer, str → string (sanity for the type ladder used by (3)/(4))."""
    cols = declare_attributes([{"id": "m1", "name": "Al", "atoms": 3, "phase": "fcc"}])
    assert ("atoms", "integer") in cols
    assert ("phase", "string") in cols


def test_edge_has_integer_id_and_source_target() -> None:
    """(5) An edge gets an integer 'id' plus source/target attributes."""
    xml = gexf_document(
        [{"id": "m1", "name": "Al"}, {"id": "m2", "name": "Cu"}],
        [{"source": "m1", "target": "m2"}],
    )
    assert '<edge id="0" source="m1" target="m2"/>' in xml


def test_edge_count_matches_len_edges() -> None:
    """(6) The count of '<edge ' occurrences equals len(edges)."""
    nodes = [{"id": "m1", "name": "Al"}, {"id": "m2", "name": "Cu"}, {"id": "m3", "name": "Fe"}]
    edges = [
        {"source": "m1", "target": "m2"},
        {"source": "m2", "target": "m3"},
        {"source": "m1", "target": "m3"},
    ]
    xml = gexf_document(nodes, edges)
    # '<edge ' (trailing space) matches each element but NOT the '<edges>' container.
    assert xml.count("<edge ") == len(edges)
    assert "<edges>" in xml


def test_label_xml_escaping() -> None:
    """(7) A '<' in a label is escaped to '&lt;' (and no raw '<B' leaks into the XML)."""
    xml = gexf_document([{"id": "m1", "name": "A<B"}], [])
    assert 'label="A&lt;B"' in xml
    assert "A<B" not in xml


def test_attr_columns_first_seen_deterministic() -> None:
    """(8) attr_columns order is first-seen deterministic across nodes."""
    nodes = [
        {"id": "m1", "name": "Al", "hardness": 5.0, "phase": "fcc"},
        {"id": "m2", "name": "Cu", "phase": "fcc", "atoms": 4},
        {"id": "m3", "name": "Fe", "hardness": 9.0},
    ]
    cols = declare_attributes(nodes)
    names = [name for name, _t in cols]
    assert names == ["hardness", "phase", "atoms"]
    # to_gexf reuses declare_attributes, so its columns match exactly.
    assert to_gexf(nodes, []).attr_columns == tuple(cols)


def test_as_dict_roundtrips_columns_and_xml() -> None:
    """GexfDoc.as_dict() exposes (name, type) pairs and the XML verbatim."""
    doc = to_gexf([{"id": "m1", "name": "Al", "hardness": 5.0}], [])
    payload = doc.as_dict()
    assert ("hardness", "double") in payload["attr_columns"]
    assert payload["xml"] == doc.xml
    assert '<attvalue for="0" value="5.0"/>' in doc.xml

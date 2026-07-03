"""Tests for the Neo4j bulk-import CSV generator (§22.6).

Hand-checkable: every expected header / row / CSV line is written out literally.
"""

from __future__ import annotations

from kg_retrievers.neo4j_import_csv import (
    ImportBundle,
    build_bundle,
    node_columns,
    nodes_csv,
    rels_csv,
)

# A small, fully hand-checkable graph: two Materials with a shared `name` prop, one of
# which also carries a float `hardness`, plus one HAS edge.
NODES = [
    {"id": "m1", "label": "Material", "props": {"name": "Al", "hardness": 9.0}},
    {"id": "m2", "label": "Material", "props": {"name": "Cu"}},
]
EDGES = [{"start": "s", "end": "t", "type": "HAS"}]


def test_node_columns_first_and_last() -> None:
    """Assertion 1: first column is ``id:ID`` and last is ``:LABEL``."""
    cols = node_columns(NODES)
    assert cols[0] == "id:ID"
    assert cols[-1] == ":LABEL"


def test_float_prop_typed_as_double() -> None:
    """Assertion 2: a float prop ``hardness`` appears as ``hardness:double``."""
    cols = node_columns(NODES)
    assert "hardness:double" in cols
    # Full expected ordering: id, first-seen str prop, first-seen float prop, label.
    assert cols == ["id:ID", "name", "hardness:double", ":LABEL"]


def test_node_row_aligned_to_header() -> None:
    """Assertion 3: node m1 (name=Al) renders aligned row, empty cell for m2 hardness."""
    bundle = build_bundle(NODES, EDGES)
    # header == id:ID, name, hardness:double, :LABEL
    assert bundle.node_rows[0] == ("m1", "Al", "9.0", "Material")
    # m2 lacks `hardness` -> empty cell in that column.
    assert bundle.node_rows[1] == ("m2", "Cu", "", "Material")


def test_material_name_only_row() -> None:
    """Assertion 3 (spec literal): id=m1 name=Al with a name-only header -> row triple."""
    nodes = [{"id": "m1", "label": "Material", "props": {"name": "Al"}}]
    bundle = build_bundle(nodes, [])
    assert bundle.node_header == ("id:ID", "name", ":LABEL")
    assert bundle.node_rows[0] == ("m1", "Al", "Material")


def test_rel_header_fixed() -> None:
    """Assertion 4: the relationship header is the fixed reserved triple."""
    bundle = build_bundle(NODES, EDGES)
    assert bundle.rel_header == (":START_ID", ":END_ID", ":TYPE")


def test_rel_row() -> None:
    """Assertion 5: edge s->t HAS renders as ``('s', 't', 'HAS')``."""
    bundle = build_bundle(NODES, EDGES)
    assert bundle.rel_rows == (("s", "t", "HAS"),)


def test_nodes_csv_first_line_is_header() -> None:
    """Assertion 6: the first CSV line equals the comma-joined node header."""
    bundle = build_bundle(NODES, EDGES)
    text = nodes_csv(bundle)
    first_line = text.split("\n")[0]
    assert first_line == ",".join(bundle.node_header)
    assert first_line == "id:ID,name,hardness:double,:LABEL"


def test_missing_prop_empty_cell() -> None:
    """Assertion 7: a node missing a property renders an empty cell for that column."""
    bundle = build_bundle(NODES, EDGES)
    # m2 has no hardness -> column index 2 is empty.
    assert bundle.node_rows[1][2] == ""
    # And it shows up as a trailing empty field in the CSV line: "m2,Cu,,Material".
    lines = nodes_csv(bundle).split("\n")
    assert "m2,Cu,,Material" in lines


def test_empty_input() -> None:
    """Assertion 8: empty input -> no rows and a header-only CSV."""
    bundle = build_bundle([], [])
    assert bundle.node_rows == ()
    assert bundle.rel_rows == ()
    # node header still carries the two reserved columns.
    assert bundle.node_header == ("id:ID", ":LABEL")
    text = nodes_csv(bundle)
    # Exactly one non-empty line (the header), then the trailing terminator.
    assert text == "id:ID,:LABEL\n"
    assert text.rstrip("\n") == "id:ID,:LABEL"


def test_rels_csv_first_line() -> None:
    """rels_csv starts with the fixed relationship header line."""
    bundle = build_bundle(NODES, EDGES)
    text = rels_csv(bundle)
    lines = text.split("\n")
    assert lines[0] == ":START_ID,:END_ID,:TYPE"
    assert lines[1] == "s,t,HAS"


def test_bundle_as_dict_roundtrip_shape() -> None:
    """as_dict() exposes all four fields as plain lists in §22.6 order."""
    bundle = build_bundle(NODES, EDGES)
    d = bundle.as_dict()
    assert list(d.keys()) == ["node_header", "node_rows", "rel_header", "rel_rows"]
    assert d["node_header"] == ["id:ID", "name", "hardness:double", ":LABEL"]
    assert d["node_rows"][0] == ["m1", "Al", "9.0", "Material"]
    assert d["rel_header"] == [":START_ID", ":END_ID", ":TYPE"]
    assert d["rel_rows"] == [["s", "t", "HAS"]]


def test_int_and_bool_prop_types() -> None:
    """int props tag ``:long``, bool props tag ``:boolean`` and render true/false."""
    nodes = [
        {"id": "n1", "label": "Sample", "props": {"count": 3, "active": True}},
        {"id": "n2", "label": "Sample", "props": {"count": 5, "active": False}},
    ]
    bundle = build_bundle(nodes, [])
    assert bundle.node_header == ("id:ID", "count:long", "active:boolean", ":LABEL")
    assert bundle.node_rows[0] == ("n1", "3", "true", "Sample")
    assert bundle.node_rows[1] == ("n2", "5", "false", "Sample")


def test_frozen_bundle_immutable() -> None:
    """ImportBundle is frozen: attribute assignment is rejected."""
    bundle = build_bundle(NODES, EDGES)
    assert isinstance(bundle, ImportBundle)
    try:
        bundle.node_header = ()  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - would signal a non-frozen dataclass
        raise AssertionError("ImportBundle must be frozen")

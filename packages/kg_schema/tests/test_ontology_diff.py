"""Tests for ontology diff — §3.22 (hand-checked expected values)."""

from __future__ import annotations

from kg_schema.ontology_diff import OntologyDiff, diff_edges, diff_labels

# -- fixtures: small hand-checkable label / edge sets --
A_LABELS = {"Material", "Property", "Sample"}
B_LABELS = {"Material", "Property", "Facility"}  # -Sample, +Facility

A_EDGES = [
    ("Material", "HAS_COMPOSITION", "Composition"),
    ("Sample", "HAS_MATERIAL", "Material"),
]
B_EDGES = [
    ("Material", "HAS_COMPOSITION", "Composition"),  # common
    ("Facility", "LOCATED_IN", "Country"),  # added
]


def test_added_labels() -> None:
    d = diff_labels(A_LABELS, B_LABELS)
    assert d["added"] == frozenset({"Facility"})


def test_removed_labels() -> None:
    d = diff_labels(A_LABELS, B_LABELS)
    assert d["removed"] == frozenset({"Sample"})
    assert d["common"] == frozenset({"Material", "Property"})


def test_no_change_labels() -> None:
    d = diff_labels(A_LABELS, A_LABELS)
    assert d["added"] == frozenset()
    assert d["removed"] == frozenset()
    assert d["common"] == frozenset(A_LABELS)


def test_edge_diff() -> None:
    d = diff_edges(A_EDGES, B_EDGES)
    assert d["added"] == frozenset({("Facility", "LOCATED_IN", "Country")})
    assert d["removed"] == frozenset({("Sample", "HAS_MATERIAL", "Material")})
    assert d["common"] == frozenset({("Material", "HAS_COMPOSITION", "Composition")})


def test_edge_diff_dedupes_duplicates() -> None:
    dup = [("Material", "HAS_COMPOSITION", "Composition")] * 3
    d = diff_edges(dup, [])
    assert d["removed"] == frozenset({("Material", "HAS_COMPOSITION", "Composition")})
    assert d["added"] == frozenset()


def test_symmetric_added_equals_reversed_removed() -> None:
    fwd = diff_labels(A_LABELS, B_LABELS)
    rev = diff_labels(B_LABELS, A_LABELS)
    assert fwd["added"] == rev["removed"]
    assert fwd["removed"] == rev["added"]
    assert fwd["common"] == rev["common"]


def test_ontology_diff_as_dict() -> None:
    diff = OntologyDiff.compare(A_LABELS, B_LABELS, A_EDGES, B_EDGES)
    d = diff.as_dict()
    assert d["added_labels"] == ["Facility"]
    assert d["removed_labels"] == ["Sample"]
    assert d["common_labels"] == ["Material", "Property"]
    assert d["added_edges"] == [["Facility", "LOCATED_IN", "Country"]]
    assert d["removed_edges"] == [["Sample", "HAS_MATERIAL", "Material"]]
    assert d["common_edges"] == [["Material", "HAS_COMPOSITION", "Composition"]]


def test_ontology_diff_frozen_and_changed_flag() -> None:
    diff = OntologyDiff.compare(A_LABELS, B_LABELS, A_EDGES, B_EDGES)
    assert diff.changed is True
    same = OntologyDiff.compare(A_LABELS, A_LABELS, A_EDGES, A_EDGES)
    assert same.changed is False
    # frozen dataclass: assignment must raise.
    try:
        diff.added_labels = frozenset()  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("OntologyDiff must be frozen")


def test_compare_matches_component_functions() -> None:
    diff = OntologyDiff.compare(A_LABELS, B_LABELS, A_EDGES, B_EDGES)
    assert diff.added_labels == diff_labels(A_LABELS, B_LABELS)["added"]
    assert diff.added_edges == diff_edges(A_EDGES, B_EDGES)["added"]

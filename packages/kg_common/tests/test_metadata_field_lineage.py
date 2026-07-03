"""Field / column-level lineage builder tests (§10.5)."""

from __future__ import annotations

from kg_common.metadata.field_lineage import (
    FieldEdge,
    FieldLineage,
    build_field_lineage,
)


def test_field_edge_as_dict() -> None:
    edge = FieldEdge("a", "b")
    assert edge.as_dict() == {"source_field": "a", "target_field": "b"}


def test_build_basic_mapping() -> None:
    fl = build_field_lineage(
        {
            "comp.value": ["Composition.value", "Composition.raw"],
            "comp.unit": ["Composition.unit"],
        }
    )
    assert isinstance(fl, FieldLineage)
    assert len(fl.edges) == 3


def test_targets_of_is_sorted() -> None:
    fl = build_field_lineage(
        {
            "comp.value": ["Composition.value", "Composition.raw"],
            "comp.unit": ["Composition.unit"],
        }
    )
    # Insertion order was value, raw — result must be sorted alphabetically.
    assert fl.targets_of("comp.value") == ("Composition.raw", "Composition.value")


def test_sources_of_single() -> None:
    fl = build_field_lineage(
        {
            "comp.value": ["Composition.value", "Composition.raw"],
            "comp.unit": ["Composition.unit"],
        }
    )
    assert fl.sources_of("Composition.unit") == ("comp.unit",)


def test_targets_of_missing_returns_empty() -> None:
    fl = build_field_lineage({"comp.unit": ["Composition.unit"]})
    assert fl.targets_of("missing") == ()


def test_sources_of_missing_returns_empty() -> None:
    fl = build_field_lineage({"comp.unit": ["Composition.unit"]})
    assert fl.sources_of("missing") == ()


def test_duplicate_targets_collapse() -> None:
    fl = build_field_lineage({"a": ["b", "b"]})
    assert len(fl.edges) == 1
    assert fl.edges[0] == FieldEdge("a", "b")


def test_lineage_as_dict_shape() -> None:
    fl = build_field_lineage(
        {
            "comp.value": ["Composition.value", "Composition.raw"],
            "comp.unit": ["Composition.unit"],
        }
    )
    dumped = fl.as_dict()
    assert isinstance(dumped["edges"], list)
    assert len(dumped["edges"]) == 3
    assert all(set(e) == {"source_field", "target_field"} for e in dumped["edges"])


def test_edges_sorted_deterministically() -> None:
    # Same mapping in a different dict order must yield identical edge tuples.
    m1 = {
        "comp.value": ["Composition.value", "Composition.raw"],
        "comp.unit": ["Composition.unit"],
    }
    m2 = {
        "comp.unit": ["Composition.unit"],
        "comp.value": ["Composition.raw", "Composition.value"],
    }
    fl1 = build_field_lineage(m1)
    fl2 = build_field_lineage(m2)
    assert fl1.edges == fl2.edges
    keys = [(e.source_field, e.target_field) for e in fl1.edges]
    assert keys == sorted(keys)
    assert keys == [
        ("comp.unit", "Composition.unit"),
        ("comp.value", "Composition.raw"),
        ("comp.value", "Composition.value"),
    ]


def test_empty_mapping() -> None:
    fl = build_field_lineage({})
    assert fl.edges == ()
    assert fl.as_dict() == {"edges": []}

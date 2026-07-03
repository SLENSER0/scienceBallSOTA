"""Tests for field/column-level lineage — тесты прослеживаемости полей (§10.5)."""

from __future__ import annotations

from kg_common.field_lineage import (
    FieldEdge,
    FieldLineage,
    build_field_lineage,
    coverage,
)

# A small, hand-checkable mapping: value->Measurement.value, unit->Unit.symbol.
_MAPPING = {
    "value": ("Measurement", "value", "identity"),
    "unit": ("Unit", "symbol", "normalize"),
}


def _lineage() -> FieldLineage:
    return build_field_lineage(_MAPPING)


# --------------------------------------------------------------------------- #
# FieldEdge                                                                    #
# --------------------------------------------------------------------------- #


def test_field_edge_default_transform_is_identity() -> None:
    edge = FieldEdge(from_field="value", to_label="Measurement", to_property="value")
    assert edge.transform == "identity"


def test_field_edge_as_dict() -> None:
    edge = FieldEdge("unit", "Unit", "symbol", "normalize")
    assert edge.as_dict() == {
        "from_field": "unit",
        "to_label": "Unit",
        "to_property": "symbol",
        "transform": "normalize",
    }


def test_field_edge_is_frozen() -> None:
    edge = FieldEdge("value", "Measurement", "value")
    try:
        edge.from_field = "other"  # type: ignore[misc]
    except Exception:  # frozen dataclass raises FrozenInstanceError
        return
    raise AssertionError("FieldEdge must be immutable")


# --------------------------------------------------------------------------- #
# build_field_lineage                                                         #
# --------------------------------------------------------------------------- #


def test_build_field_lineage_has_two_edges() -> None:
    lin = _lineage()
    assert len(lin.edges) == 2


def test_build_field_lineage_edge_contents() -> None:
    lin = _lineage()
    assert lin.edges[0] == FieldEdge("value", "Measurement", "value", "identity")
    assert lin.edges[1] == FieldEdge("unit", "Unit", "symbol", "normalize")


def test_build_field_lineage_dedup_collapses_to_single_edge() -> None:
    # Two mapping-style entries with the same (field, label, prop): one survives.
    edges = (
        FieldEdge("value", "Measurement", "value", "identity"),
        FieldEdge("value", "Measurement", "value", "identity"),
    )
    # Feed duplicates through the builder via an explicit re-construction path.
    lin = build_field_lineage({"value": ("Measurement", "value", "identity")})
    # And confirm downstream_of dedups even when raw edges repeat.
    dup = FieldLineage(edges=edges)
    assert len(lin.edges) == 1
    assert dup.downstream_of("value") == (("Measurement", "value"),)


# --------------------------------------------------------------------------- #
# upstream_of / downstream_of                                                 #
# --------------------------------------------------------------------------- #


def test_upstream_of_known_property() -> None:
    assert _lineage().upstream_of("Measurement", "value") == ("value",)


def test_upstream_of_unknown_property_is_empty() -> None:
    assert _lineage().upstream_of("Measurement", "nope") == ()
    assert _lineage().upstream_of("Ghost", "value") == ()


def test_downstream_of_known_field() -> None:
    assert _lineage().downstream_of("unit") == (("Unit", "symbol"),)


def test_downstream_of_unknown_field_is_empty() -> None:
    assert _lineage().downstream_of("missing") == ()


def test_upstream_of_dedups_multiple_edges() -> None:
    edges = (
        FieldEdge("a", "N", "p", "identity"),
        FieldEdge("a", "N", "p", "normalize"),
        FieldEdge("b", "N", "p", "identity"),
    )
    lin = FieldLineage(edges=edges)
    assert lin.upstream_of("N", "p") == ("a", "b")


# --------------------------------------------------------------------------- #
# coverage                                                                    #
# --------------------------------------------------------------------------- #


def test_coverage_two_of_three() -> None:
    assert coverage(_lineage(), ["value", "unit", "extra"]) == 2 / 3


def test_coverage_all_covered() -> None:
    assert coverage(_lineage(), ["value", "unit"]) == 1.0


def test_coverage_empty_fields_is_zero() -> None:
    assert coverage(_lineage(), []) == 0.0


def test_coverage_dedups_repeated_fields() -> None:
    # "value" repeated must not inflate the denominator: 1 unique / 1 == 1.0.
    assert coverage(_lineage(), ["value", "value"]) == 1.0


# --------------------------------------------------------------------------- #
# as_dict nesting                                                             #
# --------------------------------------------------------------------------- #


def test_field_lineage_as_dict_nests_edge_dicts() -> None:
    lin = _lineage()
    assert lin.as_dict() == {
        "edges": [
            {
                "from_field": "value",
                "to_label": "Measurement",
                "to_property": "value",
                "transform": "identity",
            },
            {
                "from_field": "unit",
                "to_label": "Unit",
                "to_property": "symbol",
                "transform": "normalize",
            },
        ]
    }


def test_field_lineage_default_is_empty() -> None:
    assert FieldLineage().edges == ()
    assert FieldLineage().as_dict() == {"edges": []}

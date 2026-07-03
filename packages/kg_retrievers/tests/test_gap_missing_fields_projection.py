"""Hand-checkable tests for the §15.2 missing_fields projection."""

from __future__ import annotations

from kg_retrievers.gap_missing_fields_projection import (
    GAP_TYPE_TO_FIELD,
    EntityMissingFields,
    project_missing_fields,
)


def _gap(gap_id: str, entity_id: str, gap_type: str, status: str = "open") -> dict:
    return {
        "gap_id": gap_id,
        "about_entity_id": entity_id,
        "gap_type": gap_type,
        "status": status,
    }


def test_single_missing_unit_gap() -> None:
    gaps = [_gap("g1", "e1", "missing_unit")]
    result = project_missing_fields(gaps)
    assert result["e1"].missing_fields == ("unit",)
    assert result["e1"].gap_ids == ("g1",)


def test_two_gaps_fields_sorted() -> None:
    gaps = [
        _gap("g1", "e1", "missing_unit"),
        _gap("g2", "e1", "missing_baseline"),
    ]
    result = project_missing_fields(gaps)
    # sorted: 'baseline_value' < 'unit'
    assert result["e1"].missing_fields == ("baseline_value", "unit")


def test_resolved_gap_excluded_by_default_included_when_all() -> None:
    gaps = [_gap("g1", "e1", "missing_unit", status="resolved")]
    assert "e1" not in project_missing_fields(gaps)  # open_only=True
    result = project_missing_fields(gaps, open_only=False)
    assert result["e1"].missing_fields == ("unit",)


def test_duplicate_type_field_deduped_gap_ids_kept() -> None:
    gaps = [
        _gap("g1", "e1", "missing_unit"),
        _gap("g2", "e1", "missing_unit"),
    ]
    result = project_missing_fields(gaps)
    assert result["e1"].missing_fields == ("unit",)
    assert len(result["e1"].gap_ids) == 2
    assert set(result["e1"].gap_ids) == {"g1", "g2"}


def test_unmapped_gap_type_absent() -> None:
    gaps = [_gap("g1", "e1", "totally_unknown_type")]
    assert project_missing_fields(gaps) == {}


def test_unmapped_type_entity_absent_but_others_present() -> None:
    gaps = [
        _gap("g1", "e1", "totally_unknown_type"),
        _gap("g2", "e2", "missing_source_span"),
    ]
    result = project_missing_fields(gaps)
    assert "e1" not in result
    assert result["e2"].missing_fields == ("source_span",)


def test_as_dict_keys() -> None:
    emf = EntityMissingFields(
        entity_id="e1",
        missing_fields=("unit",),
        gap_ids=("g1",),
    )
    d = emf.as_dict()
    assert set(d) == {"entity_id", "missing_fields", "gap_ids"}
    assert d == {
        "entity_id": "e1",
        "missing_fields": ["unit"],
        "gap_ids": ["g1"],
    }


def test_gap_type_table_contract() -> None:
    assert GAP_TYPE_TO_FIELD["missing_unit"] == "unit"
    assert GAP_TYPE_TO_FIELD["missing_baseline"] == "baseline_value"
    assert GAP_TYPE_TO_FIELD["missing_source_span"] == "source_span"
    assert GAP_TYPE_TO_FIELD["missing_processing_parameter"] == "processing_parameter"

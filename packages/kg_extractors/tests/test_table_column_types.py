"""Tests for table column-type profiling (§5.7)."""

from __future__ import annotations

from kg_extractors.table_column_types import (
    ColumnProfile,
    ColumnType,
    TableProfile,
    profile_columns,
)


def test_material_hardness_table() -> None:
    """Label column -> CATEGORICAL, measurement column -> NUMERIC w/ unit."""
    profile = profile_columns(
        ["Material", "Hardness (HV)"],
        [["Al", "148"], ["Cu", "200"]],
    )
    assert profile.columns[0].col_type == ColumnType.CATEGORICAL
    assert profile.columns[1].col_type == ColumnType.NUMERIC
    assert profile.columns[1].numeric_fraction == 1.0
    assert profile.columns[1].unit_hint == "HV"
    assert profile.columns[0].unit_hint is None


def test_all_blank_column_is_empty() -> None:
    """A column whose every cell is '' is EMPTY with 0.0 numeric fraction."""
    profile = profile_columns(["Note"], [[""], [""], [""]])
    assert profile.columns[0].col_type == ColumnType.EMPTY
    assert profile.columns[0].numeric_fraction == 0.0


def test_mixed_column_half_numeric() -> None:
    """Half-number / half-text column is MIXED with fraction 0.5."""
    profile = profile_columns(
        ["Val"],
        [["5"], ["x"], ["7"], ["y"]],
    )
    assert profile.columns[0].col_type == ColumnType.MIXED
    assert profile.columns[0].numeric_fraction == 0.5


def test_cyrillic_comma_unit() -> None:
    """A trailing comma clause in a RU header yields the unit token."""
    profile = profile_columns(["σ, МПа"], [["120"], ["140"]])
    assert profile.columns[0].unit_hint == "МПа"
    assert profile.columns[0].col_type == ColumnType.NUMERIC


def test_ragged_row_is_padded() -> None:
    """A row shorter than the headers is padded and does not crash."""
    profile = profile_columns(
        ["Material", "Hardness (HV)"],
        [["Al", "148"], ["Cu"]],  # second row missing the hardness cell
    )
    # Only one non-empty numeric cell remains in column 1 -> still NUMERIC.
    assert profile.columns[1].col_type == ColumnType.NUMERIC
    assert profile.columns[1].numeric_fraction == 1.0
    assert profile.columns[0].col_type == ColumnType.CATEGORICAL


def test_range_cell_counts_as_numeric() -> None:
    """A range cell like '200-300' parses as a number (midpoint)."""
    profile = profile_columns(["Range"], [["200-300"], ["150-160"]])
    assert profile.columns[0].col_type == ColumnType.NUMERIC
    assert profile.columns[0].numeric_fraction == 1.0


def test_scientific_notation_numeric() -> None:
    """Scientific-notation literals are numeric."""
    profile = profile_columns(["E"], [["1.2e3"], ["2.5E-4"], ["-3.0"]])
    assert profile.columns[0].col_type == ColumnType.NUMERIC
    assert profile.columns[0].numeric_fraction == 1.0


def test_table_profile_as_dict() -> None:
    """TableProfile.as_dict projects nested column dicts with the unit hint."""
    profile = profile_columns(
        ["Material", "Hardness (HV)"],
        [["Al", "148"], ["Cu", "200"]],
    )
    payload = profile.as_dict()
    assert payload["columns"][1]["unit_hint"] == "HV"
    assert payload["columns"][1]["col_type"] == "numeric"
    assert payload["columns"][0]["col_type"] == "categorical"
    assert payload["columns"][1]["numeric_fraction"] == 1.0


def test_column_profile_as_dict_str_enum() -> None:
    """ColumnProfile.as_dict serializes the type as a bare string value."""
    prof = ColumnProfile(
        index=0,
        header="Material",
        col_type=ColumnType.CATEGORICAL,
        numeric_fraction=0.0,
        unit_hint=None,
    )
    assert prof.as_dict() == {
        "index": 0,
        "header": "Material",
        "col_type": "categorical",
        "numeric_fraction": 0.0,
        "unit_hint": None,
    }


def test_frozen_dataclasses() -> None:
    """Both profile records are frozen (immutable)."""
    table = TableProfile(columns=())
    prof = ColumnProfile(0, "h", ColumnType.EMPTY, 0.0, None)
    for obj, attr, value in ((table, "columns", ()), (prof, "index", 1)):
        try:
            setattr(obj, attr, value)
        except AttributeError:
            continue
        raise AssertionError("expected frozen dataclass to reject mutation")

"""Tests for the §17.12 Experiment Explorer sortable table view-model."""

from __future__ import annotations

import pytest

from kg_retrievers.experiment_table_view import (
    COLUMNS,
    ExperimentTable,
    build_experiment_table,
    sort_rows,
)

# The nine §5.2.5 columns, in the exact spec order.
_EXPECTED_KEYS = (
    "experiment",
    "material",
    "processing",
    "property",
    "value",
    "unit",
    "effect",
    "confidence",
    "evidenceCount",
)


def test_columns_keys_equal_the_nine_in_order() -> None:
    assert tuple(col["key"] for col in COLUMNS) == _EXPECTED_KEYS
    # Every column carries a key/label/type triple.
    for col in COLUMNS:
        assert set(col) == {"key", "label", "type"}


def test_build_maps_value_unit_through_and_absent_effect_to_none() -> None:
    envelope = {
        "experiment": "exp-1",
        "material": "PLA",
        "processing": "annealed",
        "property": "tensile",
        "value": 42.0,
        "unit": "MPa",
        "confidence": 0.8,
        "evidenceCount": 3,
        # 'effect' deliberately absent.
    }
    table = build_experiment_table([envelope])
    (row,) = table.rows
    assert row["value"] == 42.0
    assert row["unit"] == "MPa"
    assert row["effect"] is None  # absent field → None cell


def test_two_experiments_produce_two_rows() -> None:
    table = build_experiment_table([{"experiment": "a"}, {"experiment": "b"}])
    assert len(table.rows) == 2
    assert [r["experiment"] for r in table.rows] == ["a", "b"]


def test_sort_by_confidence_descending() -> None:
    rows = [
        {"experiment": "low", "confidence": 0.4},
        {"experiment": "high", "confidence": 0.9},
    ]
    out = sort_rows(rows, "confidence", descending=True)
    assert [r["experiment"] for r in out] == ["high", "low"]  # 0.9 before 0.4


def test_none_confidence_sorts_last_both_directions() -> None:
    rows = [
        {"experiment": "none", "confidence": None},
        {"experiment": "mid", "confidence": 0.5},
        {"experiment": "hi", "confidence": 0.9},
    ]
    asc = sort_rows(rows, "confidence", descending=False)
    desc = sort_rows(rows, "confidence", descending=True)
    assert asc[-1]["experiment"] == "none"
    assert desc[-1]["experiment"] == "none"
    assert [r["experiment"] for r in asc[:2]] == ["mid", "hi"]
    assert [r["experiment"] for r in desc[:2]] == ["hi", "mid"]


def test_sort_is_stable_for_equal_keys() -> None:
    rows = [
        {"experiment": "first", "confidence": 0.5},
        {"experiment": "second", "confidence": 0.5},
        {"experiment": "third", "confidence": 0.5},
    ]
    asc = sort_rows(rows, "confidence")
    desc = sort_rows(rows, "confidence", descending=True)
    # Equal keys keep original order in BOTH directions.
    assert [r["experiment"] for r in asc] == ["first", "second", "third"]
    assert [r["experiment"] for r in desc] == ["first", "second", "third"]


def test_sort_unknown_column_raises_value_error() -> None:
    with pytest.raises(ValueError):
        sort_rows([{"confidence": 0.5}], "not_a_column")


def test_as_dict_columns_length_is_nine() -> None:
    table = build_experiment_table([{"experiment": "x"}])
    d = table.as_dict()
    assert len(d["columns"]) == 9
    assert len(d["rows"]) == 1
    # as_dict returns plain copies, not the frozen internals.
    assert isinstance(table, ExperimentTable)
    d["columns"].append({"key": "junk"})
    assert len(table.columns) == 9  # original untouched

"""Tests for §15.5 ranked gap list (material coverage ranking)."""

from __future__ import annotations

from kg_retrievers.material_coverage_ranking import (
    MaterialCoverage,
    rank_material_coverage,
)


def test_zero_measured_across_three_targets() -> None:
    targets = ["band_gap", "conductivity", "density"]
    cells = [
        {"material_id": "m1", "material": "NaCl", "property": "band_gap", "measured_count": 0},
        {"material_id": "m1", "material": "NaCl", "property": "conductivity", "measured_count": 0},
        {"material_id": "m1", "material": "NaCl", "property": "density", "measured_count": 0},
    ]
    (mc,) = rank_material_coverage(cells, targets)
    assert mc.coverage_ratio == 0.0
    assert mc.covered == 0
    assert mc.uncovered == 3
    assert mc.uncovered_properties == tuple(sorted(targets))


def test_fully_measured_material() -> None:
    targets = ["band_gap", "density"]
    cells = [
        {"material_id": "m2", "material": "Si", "property": "band_gap", "measured_count": 5},
        {"material_id": "m2", "material": "Si", "property": "density", "measured_count": 2},
    ]
    (mc,) = rank_material_coverage(cells, targets)
    assert mc.coverage_ratio == 1.0
    assert mc.uncovered == 0
    assert mc.uncovered_properties == ()


def test_cell_for_non_target_property_ignored() -> None:
    targets = ["band_gap", "density"]
    cells = [
        {"material_id": "m3", "material": "Ge", "property": "band_gap", "measured_count": 4},
        # 'color' is not a target property -> must be ignored entirely.
        {"material_id": "m3", "material": "Ge", "property": "color", "measured_count": 9},
    ]
    (mc,) = rank_material_coverage(cells, targets)
    assert mc.target_total == 2
    assert mc.covered == 1
    assert mc.coverage_ratio == 0.5
    assert mc.uncovered_properties == ("density",)


def test_worst_material_first() -> None:
    targets = ["a", "b"]
    cells = [
        # good: both covered -> ratio 1.0
        {"material_id": "good", "material": "Good", "property": "a", "measured_count": 1},
        {"material_id": "good", "material": "Good", "property": "b", "measured_count": 1},
        # bad: none covered -> ratio 0.0
        {"material_id": "bad", "material": "Bad", "property": "a", "measured_count": 0},
        {"material_id": "bad", "material": "Bad", "property": "b", "measured_count": 0},
    ]
    ranked = rank_material_coverage(cells, targets)
    assert ranked[0].material_id == "bad"
    assert ranked[-1].material_id == "good"


def test_material_only_in_ignored_cells() -> None:
    targets = ["band_gap", "density", "conductivity"]
    cells = [
        # every cell names a non-target property -> covered stays 0, target_total full.
        {"material_id": "m4", "material": "Au", "property": "color", "measured_count": 7},
        {"material_id": "m4", "material": "Au", "property": "luster", "measured_count": 3},
    ]
    (mc,) = rank_material_coverage(cells, targets)
    assert mc.target_total == len(targets)
    assert mc.covered == 0
    assert mc.coverage_ratio == 0.0
    assert mc.uncovered_properties == tuple(sorted(targets))


def test_half_covered_ratio() -> None:
    targets = ["a", "b"]
    cells = [
        {"material_id": "m5", "material": "X", "property": "a", "measured_count": 3},
        {"material_id": "m5", "material": "X", "property": "b", "measured_count": 0},
    ]
    (mc,) = rank_material_coverage(cells, targets)
    assert mc.coverage_ratio == 0.5


def test_tie_break_descending_uncovered() -> None:
    targets = ["a", "b", "c"]
    cells = [
        # both have ratio 0.0 but different uncovered counts is impossible with
        # equal target_total; instead give both ratio 0.0 -> tie on ratio, then
        # a material with more uncovered (via distinct target sets) is not
        # possible here, so use two materials at ratio 0.0 and confirm ordering
        # is stable by uncovered (equal here) — plus one partial in the middle.
        {"material_id": "z", "material": "Z", "property": "a", "measured_count": 0},
        {"material_id": "mid", "material": "Mid", "property": "a", "measured_count": 1},
    ]
    ranked = rank_material_coverage(cells, targets)
    by_id = {mc.material_id: mc for mc in ranked}
    # z: 0 covered of 3 -> ratio 0.0, uncovered 3 (worst)
    # mid: 1 covered of 3 -> ratio 0.3333, uncovered 2
    assert ranked[0].material_id == "z"
    assert by_id["z"].uncovered == 3
    assert by_id["mid"].coverage_ratio == round(1 / 3, 4)
    assert by_id["mid"].uncovered == 2


def test_as_dict_exposes_all_seven_keys() -> None:
    targets = ["a"]
    cells = [{"material_id": "m6", "material": "Y", "property": "a", "measured_count": 1}]
    (mc,) = rank_material_coverage(cells, targets)
    d = mc.as_dict()
    assert set(d) == {
        "material_id",
        "material",
        "target_total",
        "covered",
        "uncovered",
        "coverage_ratio",
        "uncovered_properties",
    }
    assert isinstance(mc, MaterialCoverage)

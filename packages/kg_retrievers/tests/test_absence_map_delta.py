"""Tests for the absence-map delta over two snapshots (§25.11).

Hand-checkable cases: a stable covered cell, a resolved gap, a regression, and cells
that appear or disappear between snapshots. Statuses use the uppercase vocabulary the
spec's transition keys are written against (``UNKNOWN->COVERED`` etc.).
"""

from __future__ import annotations

from kg_retrievers.absence_map_delta import (
    AbsenceMapDelta,
    cell_key,
    diff_absence_maps,
)


def _cell(material_id: str, property_name: str, status: str) -> dict:
    """A minimal CoverageCell-shaped dict."""
    return {
        "material_id": material_id,
        "property_name": property_name,
        "status": status,
    }


def test_cell_key_keys_on_material_and_property() -> None:
    key = cell_key(_cell("Fe", "band_gap", "COVERED"))
    assert key == ("Fe", "band_gap")


def test_covered_to_covered_is_unchanged() -> None:
    # (1) COVERED->COVERED: unchanged==1, nothing resolved or regressed.
    before = [_cell("Fe", "band_gap", "COVERED")]
    after = [_cell("Fe", "band_gap", "COVERED")]
    d = diff_absence_maps(before, after)
    assert d.unchanged == 1
    assert d.resolved == []
    assert d.regressed == []
    assert d.transitions == {"COVERED->COVERED": 1}


def test_unknown_to_covered_is_resolved() -> None:
    # (2) UNKNOWN->COVERED lands in resolved and tallies the transition.
    before = [_cell("Fe", "band_gap", "UNKNOWN")]
    after = [_cell("Fe", "band_gap", "COVERED")]
    d = diff_absence_maps(before, after)
    assert ("Fe", "band_gap") in d.resolved
    assert d.transitions["UNKNOWN->COVERED"] == 1
    assert d.regressed == []
    assert d.unchanged == 0


def test_covered_to_possible_absence_is_regressed() -> None:
    # (3) COVERED->POSSIBLE_ABSENCE lands in regressed.
    before = [_cell("Fe", "band_gap", "COVERED")]
    after = [_cell("Fe", "band_gap", "POSSIBLE_ABSENCE")]
    d = diff_absence_maps(before, after)
    assert ("Fe", "band_gap") in d.regressed
    assert d.resolved == []
    assert d.transitions["COVERED->POSSIBLE_ABSENCE"] == 1


def test_key_only_in_after_is_new_cell() -> None:
    # (4) A key present only in after is a new cell (no transition tallied).
    before: list[dict] = []
    after = [_cell("Cu", "density", "UNKNOWN")]
    d = diff_absence_maps(before, after)
    assert d.new_cells == [("Cu", "density")]
    assert d.dropped_cells == []
    assert d.transitions == {}


def test_key_only_in_before_is_dropped_cell() -> None:
    # (5) A key present only in before is a dropped cell.
    before = [_cell("Cu", "density", "COVERED")]
    after: list[dict] = []
    d = diff_absence_maps(before, after)
    assert d.dropped_cells == [("Cu", "density")]
    assert d.new_cells == []
    assert d.transitions == {}


def test_n_before_and_n_after_match_input_lengths() -> None:
    # (6) n_before / n_after equal the input list lengths.
    before = [
        _cell("Fe", "band_gap", "COVERED"),
        _cell("Cu", "density", "UNKNOWN"),
    ]
    after = [
        _cell("Fe", "band_gap", "COVERED"),
        _cell("Cu", "density", "COVERED"),
        _cell("Ni", "melting_point", "POSSIBLE_ABSENCE"),
    ]
    d = diff_absence_maps(before, after)
    assert d.n_before == 2
    assert d.n_after == 3
    # Cu resolved, Fe unchanged, Ni new.
    assert d.resolved == [("Cu", "density")]
    assert d.unchanged == 1
    assert d.new_cells == [("Ni", "melting_point")]


def test_as_dict_shapes() -> None:
    # (7) as_dict()['transitions'] is a plain dict; resolved is a list of 2-tuples.
    before = [_cell("Fe", "band_gap", "CONFIDENT_ABSENCE")]
    after = [_cell("Fe", "band_gap", "COVERED")]
    d = diff_absence_maps(before, after)
    assert isinstance(d, AbsenceMapDelta)
    assert d.resolved == [("Fe", "band_gap")]
    assert all(isinstance(k, tuple) and len(k) == 2 for k in d.resolved)

    out = d.as_dict()
    assert type(out["transitions"]) is dict
    assert out["transitions"] == {"CONFIDENT_ABSENCE->COVERED": 1}
    # Keys are serialised as 2-element lists for JSON transport.
    assert out["resolved"] == [["Fe", "band_gap"]]

"""Tests for cross-scale hardness consistency (§7.3, ASTM E140).

RU: Тесты проверки согласованности твёрдости в разных шкалах.
EN: Hand-checkable tests for :func:`check_hardness_consistency`.
"""

from __future__ import annotations

from kg_common.units.hardness_consistency import (
    HardnessConsistency,
    check_hardness_consistency,
)


def test_two_close_hv_are_consistent() -> None:
    r = check_hardness_consistency([(300, "HV"), (310, "HV")], tol_hv=20)
    assert r.consistent is True
    assert r.spread_hv == 10.0
    assert r.outlier_indices == ()
    assert r.unconvertible == ()


def test_two_far_hv_are_inconsistent() -> None:
    r = check_hardness_consistency([(300, "HV"), (500, "HV")])
    assert r.consistent is False
    assert r.spread_hv == 200.0


def test_single_element_is_consistent_zero_spread() -> None:
    r = check_hardness_consistency([(420, "HV")])
    assert r.consistent is True
    assert r.spread_hv == 0.0
    assert r.values_hv == (420.0,)
    assert r.outlier_indices == ()


def test_empty_input_is_consistent() -> None:
    r = check_hardness_consistency([])
    assert r.consistent is True
    assert r.spread_hv == 0.0
    assert r.values_hv == ()
    assert r.unconvertible == ()


def test_unknown_scale_recorded_in_unconvertible() -> None:
    r = check_hardness_consistency([(300, "HV"), (999, "ZZ"), (305, "HV")])
    assert r.unconvertible == (1,)
    # Convertible ones (indices 0 and 2) still checked among themselves.
    assert r.values_hv == (300.0, 305.0)
    assert r.consistent is True


def test_outlier_index_is_farthest_from_median() -> None:
    # HV values 300, 305, 600 → median 305, farthest is index 2 (600).
    r = check_hardness_consistency([(300, "HV"), (305, "HV"), (600, "HV")])
    assert r.consistent is False
    assert r.spread_hv == 300.0
    assert r.outlier_indices == (2,)


def test_outlier_index_uses_original_positions_after_unconvertible() -> None:
    # index 0 unconvertible; convertibles at original indices 1,2,3.
    # HV 300, 305, 600 → median 305, farthest original index is 3.
    r = check_hardness_consistency([(50, "ZZ"), (300, "HV"), (305, "HV"), (600, "HV")])
    assert r.unconvertible == (0,)
    assert r.outlier_indices == (3,)


def test_mixed_scales_convert_to_hv() -> None:
    # 30 HRC and 285 HB both map to ~300 HV per the steel table → consistent.
    r = check_hardness_consistency([(300, "HV"), (30, "HRC"), (285, "HB")], tol_hv=5)
    assert r.consistent is True
    assert r.values_hv[0] == 300.0


def test_case_insensitive_scale() -> None:
    r = check_hardness_consistency([(300, "hv"), (305, "Hv")])
    assert r.unconvertible == ()
    assert r.consistent is True


def test_tolerance_boundary_is_inclusive() -> None:
    r = check_hardness_consistency([(300, "HV"), (325, "HV")], tol_hv=25)
    assert r.spread_hv == 25.0
    assert r.consistent is True


def test_as_dict_values_hv_is_list() -> None:
    r = check_hardness_consistency([(300, "HV"), (500, "HV")])
    d = r.as_dict()
    assert isinstance(d["values_hv"], list)
    assert d["values_hv"] == [300.0, 500.0]
    assert isinstance(d["outlier_indices"], list)
    assert isinstance(d["unconvertible"], list)
    assert d["consistent"] is False


def test_frozen_dataclass() -> None:
    r = check_hardness_consistency([(300, "HV")])
    assert isinstance(r, HardnessConsistency)
    try:
        r.consistent = False  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("HardnessConsistency must be frozen")

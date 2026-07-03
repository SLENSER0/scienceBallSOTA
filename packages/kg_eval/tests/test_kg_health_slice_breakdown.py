"""Тесты per-slice KG health breakdown (§23.24)."""

from __future__ import annotations

import pytest

from kg_eval.kg_health_score import kg_health_score
from kg_eval.kg_health_slice_breakdown import (
    SliceBreakdownReport,
    SliceHealth,
    breakdown,
)

# Два среза с разными component-bags: lab_a здоровее, lab_b хуже.
LAB_A = {"evidence_coverage": 0.95, "orphan_rate": 0.02, "duplicate_rate": 0.01}
LAB_B = {"evidence_coverage": 0.55, "orphan_rate": 0.30, "duplicate_rate": 0.20}


def test_two_slices_scores_match_direct_score_health() -> None:
    rep = breakdown({"lab_a": LAB_A, "lab_b": LAB_B})
    assert isinstance(rep, SliceBreakdownReport)
    assert rep.n == 2
    by_name = {s.slice: s for s in rep.slices}
    assert isinstance(by_name["lab_a"], SliceHealth)
    assert by_name["lab_a"].score == pytest.approx(kg_health_score(LAB_A).score)
    assert by_name["lab_b"].score == pytest.approx(kg_health_score(LAB_B).score)


def test_mean_score_is_arithmetic_mean() -> None:
    rep = breakdown({"lab_a": LAB_A, "lab_b": LAB_B})
    a = kg_health_score(LAB_A).score
    b = kg_health_score(LAB_B).score
    assert rep.mean_score == pytest.approx((a + b) / 2.0)


def test_worst_lists_lower_scoring_slice_first() -> None:
    rep = breakdown({"lab_a": LAB_A, "lab_b": LAB_B})
    # lab_b хуже -> идёт первым в worst.
    assert kg_health_score(LAB_B).score < kg_health_score(LAB_A).score
    assert rep.worst == ("lab_b", "lab_a")


def test_worst_k_truncates_to_one() -> None:
    rep = breakdown({"lab_a": LAB_A, "lab_b": LAB_B}, worst_k=1)
    assert rep.worst == ("lab_b",)


def test_all_gates_passed_false_if_any_slice_fails() -> None:
    thr = {"evidence_coverage": 0.90}  # lab_b (0.55) провалит порог.
    rep = breakdown({"lab_a": LAB_A, "lab_b": LAB_B}, thresholds=thr)
    by_name = {s.slice: s for s in rep.slices}
    assert by_name["lab_a"].gate_passed is True
    assert by_name["lab_b"].gate_passed is False
    assert rep.all_gates_passed is False


def test_all_gates_passed_true_without_thresholds() -> None:
    rep = breakdown({"lab_a": LAB_A, "lab_b": LAB_B})
    assert rep.all_gates_passed is True


def test_grade_letters_propagate() -> None:
    rep = breakdown({"lab_a": LAB_A, "lab_b": LAB_B})
    by_name = {s.slice: s for s in rep.slices}
    assert by_name["lab_a"].grade == kg_health_score(LAB_A).grade
    assert by_name["lab_b"].grade == kg_health_score(LAB_B).grade


def test_slices_sorted_by_name() -> None:
    rep = breakdown({"z_lab": LAB_A, "a_lab": LAB_B, "m_lab": LAB_A})
    names = [s.slice for s in rep.slices]
    assert names == sorted(names) == ["a_lab", "m_lab", "z_lab"]


def test_worst_ties_alphabetical() -> None:
    # Одинаковые bags -> одинаковый score -> ties разрешаются по алфавиту.
    rep = breakdown({"z_lab": LAB_A, "a_lab": LAB_A}, worst_k=2)
    assert rep.worst == ("a_lab", "z_lab")


def test_empty_raises_value_error() -> None:
    with pytest.raises(ValueError):
        breakdown({})


def test_as_dict_roundtrip() -> None:
    rep = breakdown({"lab_a": LAB_A, "lab_b": LAB_B}, worst_k=1)
    d = rep.as_dict()
    assert d["n"] == 2
    assert d["worst"] == ["lab_b"]
    assert d["all_gates_passed"] is True
    assert isinstance(d["slices"], list) and len(d["slices"]) == 2
    assert d["slices"][0]["slice"] == "lab_a"

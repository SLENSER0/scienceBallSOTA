"""Tests for inter-annotator agreement / QC разметки (§23.26)."""

from __future__ import annotations

import math

import pytest

from kg_eval.annotator_agreement import (
    AgreementReport,
    LabelAgreement,
    agreement_report,
    cohen_kappa,
    disagreement_ids,
    percent_agreement,
)


def test_identical_dicts_perfect_agreement() -> None:
    a = {"x": "M", "y": "P"}
    b = {"x": "M", "y": "P"}
    assert percent_agreement(a, b) == 1.0
    assert cohen_kappa(a, b) == 1.0
    rep = agreement_report(a, b)
    assert rep.observed_agreement == 1.0
    assert rep.cohen_kappa == 1.0
    assert rep.disagreements == ()


def test_total_disagreement_single_item() -> None:
    a = {"x": "M"}
    b = {"x": "P"}
    assert percent_agreement(a, b) == 0.0
    # po=0, pe=0 (marginals never coincide) -> kappa = (0-0)/(1-0) = 0.0
    assert cohen_kappa(a, b) == 0.0
    rep = agreement_report(a, b)
    assert rep.observed_agreement == 0.0
    assert rep.cohen_kappa == 0.0


def test_disagreement_ids_sorted_shared_only() -> None:
    a = {"c": "M", "a": "M", "b": "M", "z": "M"}
    b = {"c": "P", "a": "M", "b": "P", "z": "M"}
    # mismatches on c and b; a,z agree; ids returned sorted
    assert disagreement_ids(a, b) == ("b", "c")


def test_absent_items_ignored_in_n_items() -> None:
    a = {"x": "M", "y": "P", "only_a": "M"}
    b = {"x": "M", "y": "P", "only_b": "P"}
    rep = agreement_report(a, b)
    # shared keys are just x and y
    assert rep.n_items == 2
    assert "only_a" not in rep.disagreements
    assert "only_b" not in rep.disagreements


def test_per_label_agreed_count_mixed() -> None:
    # shared: i1 both M, i2 both P, i3 a=M b=P (disagree), i4 both M
    a = {"i1": "M", "i2": "P", "i3": "M", "i4": "M"}
    b = {"i1": "M", "i2": "P", "i3": "P", "i4": "M"}
    rep = agreement_report(a, b)
    by_label = {la.label: la for la in rep.per_label}
    m = by_label["M"]
    p = by_label["P"]
    # M: a used on i1,i3,i4 -> 3; b used on i1,i4 -> 2; both-M on i1,i4 -> 2
    assert m.a_count == 3
    assert m.b_count == 2
    assert m.agreed == 2
    # P: a on i2 ->1; b on i2,i3 ->2; both-P on i2 ->1
    assert p.a_count == 1
    assert p.b_count == 2
    assert p.agreed == 1
    # observed agreement 3/4
    assert rep.observed_agreement == 0.75


def test_empty_overlap_raises() -> None:
    with pytest.raises(ValueError):
        cohen_kappa({"a": "M"}, {"b": "P"})
    with pytest.raises(ValueError):
        percent_agreement({"a": "M"}, {"b": "P"})
    with pytest.raises(ValueError):
        disagreement_ids({"a": "M"}, {"b": "P"})
    with pytest.raises(ValueError):
        agreement_report({"a": "M"}, {"b": "P"})


def test_kappa_within_bounds_and_positive() -> None:
    # Hand-checkable: n=10, po=0.8. a: 6M/4P, b: 5M/5P.
    a = {f"i{k}": lbl for k, lbl in enumerate("MMMMMMPPPP")}
    b = {f"i{k}": lbl for k, lbl in enumerate("MMMMMPPPPP")}
    # agree on i0..i4 (M/M), i6..i9 (P/P); disagree i5 (M/P) -> po=9/10
    kappa = cohen_kappa(a, b)
    assert -1.0 <= kappa <= 1.0
    # pe = (6/10)(5/10) + (4/10)(5/10) = 0.30 + 0.20 = 0.5; po=0.9
    # kappa = (0.9-0.5)/(1-0.5) = 0.8
    assert math.isclose(kappa, 0.8, rel_tol=1e-9)


def test_worse_than_chance_kappa_negative() -> None:
    # Systematic opposite labeling drives kappa below zero, staying >= -1.
    a = {"i0": "M", "i1": "M", "i2": "P", "i3": "P"}
    b = {"i0": "P", "i1": "P", "i2": "M", "i3": "M"}
    kappa = cohen_kappa(a, b)
    assert -1.0 <= kappa < 0.0


def test_as_dict_shapes() -> None:
    a = {"x": "M", "y": "P"}
    b = {"x": "M", "y": "M"}
    rep = agreement_report(a, b)
    d = rep.as_dict()
    assert "cohen_kappa" in d
    assert d["n_items"] == 2
    assert isinstance(d["per_label"], list)
    assert isinstance(d["disagreements"], list)
    la = rep.per_label[0]
    assert isinstance(la, LabelAgreement)
    lad = la.as_dict()
    assert set(lad) == {"label", "a_count", "b_count", "agreed"}
    assert isinstance(rep, AgreementReport)


def test_report_frozen() -> None:
    rep = agreement_report({"x": "M"}, {"x": "M"})
    with pytest.raises((AttributeError, TypeError)):
        rep.n_items = 99  # type: ignore[misc]

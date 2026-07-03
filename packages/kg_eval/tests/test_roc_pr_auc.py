"""Tests for answer-quality discrimination metrics — ROC/PR AUC (§18.8)."""

from __future__ import annotations

import pytest

from kg_eval.roc_pr_auc import AucReport, analyze, pr_auc, roc_auc


def test_roc_auc_partial_ordering() -> None:
    # asc ranks: 0.1F=1, 0.4T=2, 0.8F=3, 0.9T=4; pos rank sum=6
    # (6 - 2*3/2) / (2*2) = 3/4
    pairs = [(0.9, True), (0.8, False), (0.4, True), (0.1, False)]
    assert roc_auc(pairs) == 0.75


def test_roc_auc_perfect_separation() -> None:
    pairs = [(0.9, True), (0.8, True), (0.2, False), (0.1, False)]
    assert roc_auc(pairs) == 1.0


def test_pr_auc_perfect_separation() -> None:
    pairs = [(0.9, True), (0.8, True), (0.2, False), (0.1, False)]
    assert pr_auc(pairs) == 1.0


def test_pr_auc_average_precision_hand_check() -> None:
    # desc: 0.9T -> prec 1.0; 0.8F; 0.4T -> prec 2/3; avg = (1.0 + 0.6667)/2
    pairs = [(0.9, True), (0.8, False), (0.4, True), (0.1, False)]
    assert pr_auc(pairs) == pytest.approx((1.0 + 2 / 3) / 2)
    assert round(pr_auc(pairs), 4) == 0.8333


def test_roc_auc_all_same_score_is_half() -> None:
    assert roc_auc([(0.5, True), (0.5, False)]) == 0.5


def test_roc_auc_all_positive_is_half() -> None:
    assert roc_auc([(0.9, True), (0.4, True), (0.1, True)]) == 0.5


def test_roc_auc_all_negative_is_half() -> None:
    assert roc_auc([(0.9, False), (0.4, False)]) == 0.5


def test_analyze_as_dict_counts_and_rounding() -> None:
    pairs = [(0.9, True), (0.8, False), (0.4, True), (0.1, False)]
    report = analyze(pairs)
    d = report.as_dict()
    assert d["n"] == 4
    assert d["n_pos"] == 2
    assert d["n_neg"] == 2
    assert d["roc_auc"] == 0.75
    assert d["pr_auc"] == 0.8333


def test_pr_auc_no_positives_is_zero() -> None:
    assert pr_auc([(0.9, False), (0.1, False)]) == 0.0


def test_pr_auc_all_positive_is_one() -> None:
    assert pr_auc([(0.9, True), (0.1, True)]) == 1.0


def test_analyze_returns_frozen_report() -> None:
    report = analyze([(0.5, True), (0.4, False)])
    assert isinstance(report, AucReport)
    with pytest.raises(AttributeError):
        report.roc_auc = 0.1  # type: ignore[misc]


def test_mid_rank_ties_partial_credit() -> None:
    # 0.9T ranks above the tied 0.5 pair; asc ranks: 0.5F,0.5T share 1.5, 0.9T=3
    # pos rank sum = 1.5 + 3 = 4.5; n_pos=2, n_neg=1
    # (4.5 - 2*3/2) / (2*1) = 1.5/2 = 0.75
    pairs = [(0.9, True), (0.5, True), (0.5, False)]
    assert roc_auc(pairs) == 0.75


def test_empty_input_raises() -> None:
    with pytest.raises(ValueError):
        roc_auc([])
    with pytest.raises(ValueError):
        pr_auc([])
    with pytest.raises(ValueError):
        analyze([])

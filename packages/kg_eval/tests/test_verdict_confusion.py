"""Tests for the multi-class verdict confusion matrix (§25.15)."""

from __future__ import annotations

import pytest

from kg_eval.verdict_confusion import VerdictConfusion, verdict_confusion


def test_perfect_diagonal_accuracy_and_macro_f1() -> None:
    """(1) Perfect 4-item diagonal -> accuracy == 1.0 and macro_f1 == 1.0."""
    labels = ["genuine_gap", "possible_miss", "retracted", "abstain"]
    result = verdict_confusion(labels, labels)
    assert result.accuracy == 1.0
    assert result.macro_f1 == 1.0
    assert isinstance(result, VerdictConfusion)


def test_off_diagonal_confusion_cell() -> None:
    """(2) matrix['genuine_gap']['possible_miss'] == 1 for one such confusion."""
    y_true = ["genuine_gap", "possible_miss"]
    y_pred = ["possible_miss", "possible_miss"]
    result = verdict_confusion(y_true, y_pred)
    assert result.matrix["genuine_gap"]["possible_miss"] == 1


def test_support_counts_true_occurrences() -> None:
    """(3) per_label['genuine_gap']['support'] counts true occurrences."""
    y_true = ["genuine_gap", "genuine_gap", "abstain"]
    y_pred = ["genuine_gap", "abstain", "abstain"]
    result = verdict_confusion(y_true, y_pred)
    assert result.per_label["genuine_gap"]["support"] == 2.0


def test_precision_predicted_twice_correct_once() -> None:
    """(4) Precision of a label predicted twice but correct once == 0.5."""
    # 'abstain' predicted twice; correct on the first, wrong on the second.
    y_true = ["abstain", "genuine_gap"]
    y_pred = ["abstain", "abstain"]
    result = verdict_confusion(y_true, y_pred)
    assert result.per_label["abstain"]["precision"] == 0.5


def test_mismatched_lengths_raise() -> None:
    """(5) Mismatched lengths raise ValueError."""
    with pytest.raises(ValueError):
        verdict_confusion(["genuine_gap"], ["genuine_gap", "abstain"])


def test_zero_support_label_f1_zero_no_zerodiv() -> None:
    """(6) A label with zero support yields f1 == 0.0 without ZeroDivision."""
    # 'retracted' is in the label space but never appears as truth or prediction.
    y_true = ["genuine_gap", "abstain"]
    y_pred = ["genuine_gap", "abstain"]
    result = verdict_confusion(y_true, y_pred, labels=["genuine_gap", "abstain", "retracted"])
    assert result.per_label["retracted"]["support"] == 0.0
    assert result.per_label["retracted"]["f1"] == 0.0
    assert result.per_label["retracted"]["precision"] == 0.0
    assert result.per_label["retracted"]["recall"] == 0.0


def test_accuracy_two_of_four() -> None:
    """(7) Accuracy of 2/4 correct == 0.5."""
    y_true = ["genuine_gap", "possible_miss", "retracted", "abstain"]
    y_pred = ["genuine_gap", "possible_miss", "abstain", "genuine_gap"]
    result = verdict_confusion(y_true, y_pred)
    assert result.accuracy == 0.5


def test_as_dict_labels_equal_resolved_order() -> None:
    """(8) as_dict()['labels'] equals the resolved label ordering."""
    # Observed in scrambled order; canonical verdicts must sort to canonical order.
    y_true = ["abstain", "genuine_gap", "retracted"]
    y_pred = ["retracted", "genuine_gap", "possible_miss"]
    result = verdict_confusion(y_true, y_pred)
    assert result.labels == ["genuine_gap", "possible_miss", "retracted", "abstain"]
    assert result.as_dict()["labels"] == result.labels


def test_extras_appended_sorted_after_canonical() -> None:
    """Non-canonical labels are appended after canonical ones in sorted order."""
    y_true = ["zeta", "genuine_gap", "alpha"]
    y_pred = ["zeta", "genuine_gap", "alpha"]
    result = verdict_confusion(y_true, y_pred)
    assert result.labels == ["genuine_gap", "alpha", "zeta"]

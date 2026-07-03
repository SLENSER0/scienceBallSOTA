"""Binary confusion matrix + precision/recall/F1/accuracy (§18.11)."""

from __future__ import annotations

import pytest
from pytest import approx

from kg_eval.confusion_matrix import Confusion, confusion

# Canonical hand-checked example (distinct precision/recall/f1):
#   y_true = 1 1 1 1 0 0
#   y_pred = 1 1 0 0 1 0
#   -> (1,1)tp (1,1)tp (1,0)fn (1,0)fn (0,1)fp (0,0)tn
#   tp=2 fp=1 fn=2 tn=1  total=6
_TRUE = [1, 1, 1, 1, 0, 0]
_PRED = [1, 1, 0, 0, 1, 0]


def test_exact_counts() -> None:
    c = confusion(_TRUE, _PRED)
    assert (c.tp, c.fp, c.fn, c.tn) == (2, 1, 2, 1)
    assert c.total == 6


def test_precision_recall_f1_accuracy_hand_values() -> None:
    c = confusion(_TRUE, _PRED)
    assert c.precision == approx(2 / 3)  # tp/(tp+fp) = 2/3
    assert c.recall == approx(1 / 2)  # tp/(tp+fn) = 2/4
    assert c.f1 == approx(4 / 7)  # 2pr/(p+r) = (2/3) / (7/6)
    assert c.accuracy == approx(1 / 2)  # (tp+tn)/total = 3/6


def test_f1_is_harmonic_mean_of_precision_recall() -> None:
    c = confusion(_TRUE, _PRED)
    harmonic = 2 / (1 / c.precision + 1 / c.recall)
    assert c.f1 == approx(harmonic) == approx(4 / 7)


def test_all_correct_f1_is_one() -> None:
    c = confusion([1, 0, 1, 0, 1], [1, 0, 1, 0, 1])
    assert (c.tp, c.fp, c.fn, c.tn) == (3, 0, 0, 2)
    assert c.precision == 1.0
    assert c.recall == 1.0
    assert c.f1 == 1.0
    assert c.accuracy == 1.0


def test_all_wrong_everything_zero() -> None:
    c = confusion([1, 1, 0, 0], [0, 0, 1, 1])
    assert (c.tp, c.fp, c.fn, c.tn) == (0, 2, 2, 0)
    assert c.precision == 0.0
    assert c.recall == 0.0
    assert c.f1 == 0.0
    assert c.accuracy == 0.0


def test_empty_inputs_are_all_zeros() -> None:
    c = confusion([], [])
    assert (c.tp, c.fp, c.fn, c.tn) == (0, 0, 0, 0)
    assert c.total == 0
    assert (c.precision, c.recall, c.f1, c.accuracy) == (0.0, 0.0, 0.0, 0.0)


def test_mismatched_lengths_raise() -> None:
    with pytest.raises(ValueError, match="length mismatch"):
        confusion([1, 0, 1], [1, 0])


def test_precision_zero_when_nothing_predicted_positive() -> None:
    # tp+fp = 0 -> precision guard returns 0.0 (no ZeroDivisionError).
    c = confusion([1, 1, 0], [0, 0, 0])
    assert (c.tp, c.fp, c.fn, c.tn) == (0, 0, 2, 1)
    assert c.precision == 0.0
    assert c.recall == 0.0  # tp/(tp+fn) = 0/2
    assert c.accuracy == approx(1 / 3)


def test_recall_zero_when_no_actual_positive() -> None:
    # tp+fn = 0 -> recall guard returns 0.0.
    c = confusion([0, 0, 0], [1, 0, 0])
    assert (c.tp, c.fp, c.fn, c.tn) == (0, 1, 0, 2)
    assert c.recall == 0.0
    assert c.precision == 0.0  # tp/(tp+fp) = 0/1
    assert c.accuracy == approx(2 / 3)


def test_bool_labels_match_int_labels() -> None:
    # True == 1, False == 0 -> bool inputs classify identically to 0/1.
    c_bool = confusion([True, True, False], [True, False, False])
    c_int = confusion([1, 1, 0], [1, 0, 0])
    assert c_bool == c_int
    assert (c_bool.tp, c_bool.fp, c_bool.fn, c_bool.tn) == (1, 0, 1, 1)


def test_custom_positive_label() -> None:
    c = confusion(["yes", "no", "yes"], ["yes", "yes", "no"], positive="yes")
    assert (c.tp, c.fp, c.fn, c.tn) == (1, 1, 1, 0)
    assert c.precision == approx(1 / 2)
    assert c.recall == approx(1 / 2)
    assert c.f1 == approx(1 / 2)
    assert c.accuracy == approx(1 / 3)


def test_as_dict_keys_and_rounding() -> None:
    d = confusion(_TRUE, _PRED).as_dict()
    assert set(d) == {"tp", "fp", "fn", "tn", "precision", "recall", "f1", "accuracy"}
    assert d["tp"] == 2 and d["fp"] == 1 and d["fn"] == 2 and d["tn"] == 1
    assert d["precision"] == round(2 / 3, 4) == 0.6667
    assert d["recall"] == 0.5
    assert d["f1"] == round(4 / 7, 4) == 0.5714
    assert d["accuracy"] == 0.5


def test_frozen_dataclass_is_immutable() -> None:
    c = confusion(_TRUE, _PRED)
    assert isinstance(c, Confusion)
    with pytest.raises(AttributeError):
        c.tp = 99  # type: ignore[misc]

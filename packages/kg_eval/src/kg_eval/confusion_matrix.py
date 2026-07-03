"""Binary confusion matrix + derived classification metrics (§18.11).

Pure, deterministic, dependency-free scoring of a binary classifier's predictions
against ground-truth labels. Used for gate/pass-fail style evaluations (§15.10:
классификация «есть противоречие / нет», absence-claim verdicts) where a single
``(tp, fp, fn, tn)`` grid plus precision/recall/F1/accuracy is enough.

A label is treated as *positive* when it equals ``positive`` (default ``1``); since
``True == 1`` and ``False == 0`` in Python, mixed ``0/1`` и ``bool`` входы
классифицируются одинаково. Everything else counts as negative. ``y_true`` и
``y_pred`` must be the same length — a mismatch is a caller bug и raises
``ValueError`` rather than silently truncating.

Zero-denominator conventions: any undefined ratio (no positives predicted, no
positives present, empty inputs) collapses to ``0.0`` — so empty ``y_true``/``y_pred``
yield all-zero counts and metrics.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Confusion:
    """Binary confusion grid with derived metrics (§18.11).

    Counts (``tp``/``fp``/``fn``/``tn``) are exact integers; ``precision``,
    ``recall``, ``f1`` и ``accuracy`` are floats in ``[0.0, 1.0]``.
    """

    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    f1: float
    accuracy: float

    @property
    def total(self) -> int:
        """Number of scored pairs (``tp + fp + fn + tn``)."""
        return self.tp + self.fp + self.fn + self.tn

    def as_dict(self) -> dict[str, float | int]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "accuracy": round(self.accuracy, 4),
        }


def confusion(
    y_true: Iterable[object], y_pred: Iterable[object], positive: object = 1
) -> Confusion:
    """Build a binary :class:`Confusion` from parallel truth/prediction sequences.

    A pair ``(t, p)`` contributes to exactly one cell: ``tp`` (both positive),
    ``fp`` (predicted positive, actually negative), ``fn`` (predicted negative,
    actually positive) or ``tn`` (both negative). Positivity is ``value == positive``.

    Raises ``ValueError`` when the two sequences differ in length.
    """
    truth = list(y_true)
    pred = list(y_pred)
    if len(truth) != len(pred):
        raise ValueError(f"y_true and y_pred length mismatch: {len(truth)} != {len(pred)}")

    tp = fp = fn = tn = 0
    for t, p in zip(truth, pred, strict=True):
        actual_pos = t == positive
        pred_pos = p == positive
        if actual_pos and pred_pos:
            tp += 1
        elif not actual_pos and pred_pos:
            fp += 1
        elif actual_pos and not pred_pos:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    total = tp + fp + fn + tn
    accuracy = (tp + tn) / total if total else 0.0
    return Confusion(tp, fp, fn, tn, precision, recall, f1, accuracy)

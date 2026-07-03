"""Answer-quality operating-point / threshold sweep (§18.8).

Given ``(score, label)`` pairs — a continuous confidence ``score`` and the boolean
ground-truth ``label`` — this module sweeps every distinct score as a decision
threshold and reports the resulting operating point. The decision rule is
**predict-positive-iff ``score >= t``**: at threshold ``t`` an example counts as a
positive prediction when its score meets or exceeds ``t`` (порог отсечения).

For each threshold the confusion counts are

* ``tp`` — positives correctly predicted positive,
* ``fp`` — negatives wrongly predicted positive,
* ``fn`` — positives wrongly predicted negative (score below ``t``),

from which precision ``tp/(tp+fp)``, recall ``tp/(tp+fn)`` and the F-beta score

    ``(1 + beta**2) * P * R / (beta**2 * P + R)``

are derived (F-мера с весом полноты ``beta``). Degenerate denominators yield ``0.0``
rather than raising. Larger ``beta`` weights recall more heavily; ``beta == 1`` is the
balanced F1.

The sweep evaluates one operating point per **distinct** score and selects the point
with the highest F-beta, breaking ties toward the **lowest** threshold (the more
permissive operating point). Empty input is a caller bug and raises ``ValueError``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class OperatingPoint:
    """One threshold's confusion counts and derived metrics (§18.8).

    ``threshold`` is the decision cutoff (predict positive iff ``score >= threshold``).
    ``precision``/``recall``/``fbeta`` are the derived scores; ``tp``/``fp``/``fn`` the
    raw counts. ``as_dict`` rounds the float metrics to 4 decimals for stable output.
    """

    threshold: float
    precision: float
    recall: float
    fbeta: float
    tp: int
    fp: int
    fn: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "threshold": self.threshold,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "fbeta": round(self.fbeta, 4),
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
        }


@dataclass(frozen=True)
class SweepReport:
    """Full threshold sweep with the selected best operating point (§18.8).

    ``beta`` is the F-beta recall weight, ``points`` the per-threshold operating points
    ordered by threshold descending, and ``best`` the highest-F-beta point (ties broken
    toward the lowest threshold). ``as_dict`` nests each point via its own ``as_dict``.
    """

    beta: float
    points: tuple[OperatingPoint, ...]
    best: OperatingPoint

    def as_dict(self) -> dict[str, object]:
        return {
            "beta": self.beta,
            "points": [point.as_dict() for point in self.points],
            "best": self.best.as_dict(),
        }


def _fbeta(precision: float, recall: float, beta: float) -> float:
    """F-beta from precision/recall; ``0.0`` when the denominator vanishes."""
    beta_sq = beta * beta
    denominator = beta_sq * precision + recall
    if denominator == 0.0:
        return 0.0
    return (1.0 + beta_sq) * precision * recall / denominator


def _operating_point(
    pairs: Sequence[tuple[float, bool]], threshold: float, beta: float
) -> OperatingPoint:
    """Evaluate ``predict-positive-iff score >= threshold`` over ``pairs``."""
    tp = fp = fn = 0
    for score, label in pairs:
        predicted_positive = score >= threshold
        if label and predicted_positive:
            tp += 1
        elif not label and predicted_positive:
            fp += 1
        elif label and not predicted_positive:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return OperatingPoint(
        threshold=threshold,
        precision=precision,
        recall=recall,
        fbeta=_fbeta(precision, recall, beta),
        tp=tp,
        fp=fp,
        fn=fn,
    )


def sweep_thresholds(pairs: Sequence[tuple[float, bool]], *, beta: float = 1.0) -> SweepReport:
    """Sweep every distinct score as a threshold and pick the best F-beta point (§18.8).

    Evaluates one :class:`OperatingPoint` per distinct score under the
    predict-positive-iff ``score >= t`` rule, then selects the highest-F-beta point,
    breaking ties toward the lowest threshold. Raises ``ValueError`` on empty input.
    """
    if not pairs:
        raise ValueError("sweep_thresholds requires at least one (score, label) pair")
    thresholds = sorted({score for score, _ in pairs}, reverse=True)
    points = tuple(_operating_point(pairs, threshold, beta) for threshold in thresholds)
    best = max(points, key=lambda point: (point.fbeta, -point.threshold))
    return SweepReport(beta=beta, points=points, best=best)

"""Probability-calibration reliability diagram for absence predictions (§25.15).

Pure-stdlib scoring of how well a predicted probability ``p_truly_absent`` matches
the binary outcome — ``1`` when the entity was *truly absent* from the graph and
``0`` when the "absence" turned out to be a **miss** (the fact was present after
all). This is a *probability*-calibration view, distinct from:

* :mod:`kg_eval.answerability_metrics` — verdict-label (``genuine_gap`` /
  ``possible_miss`` / …) precision/recall, not a calibrated probability;
* :mod:`kg_eval.selective_risk_coverage` — risk-vs-coverage under an abstention
  threshold, not per-probability reliability.

Each row is a mapping ``{"p": float, "outcome": 0 | 1}`` where ``p`` is a
probability in ``[0, 1]``. We partition rows into equal-width reliability bins
and derive:

* **Brier score** — mean squared error ``(p − outcome)²`` над всеми строками
  (среднеквадратичная ошибка вероятности).
* **ECE** (expected calibration error) — sum over bins of the ``count/N``-weighted
  gap ``|mean_pred − mean_outcome|`` (средняя калибровочная ошибка).

Binning convention: equal-width bins over ``[0, 1]`` where bin ``i`` covers
``[i/n_bins, (i+1)/n_bins)``. A probability of exactly ``1.0`` is clamped into the
last bin so no row is dropped. So ``p = 0.3`` with ``n_bins = 10`` lands in bin
index ``3`` (``lo = 0.3 <= 0.3 < 0.4 = hi``). Empty bins report ``count = 0`` with
zeroed statistics and contribute nothing to ECE. Empty input is not an error: it
yields ``ece = 0.0`` и ``brier = 0.0`` with ``n = 0``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ReliabilityBin:
    """One equal-width reliability bin over ``[0, 1]`` (§25.15).

    ``lo``/``hi`` are the bin's probability bounds; ``count`` is the number of rows
    that fell into it; ``mean_pred`` is their mean predicted ``p`` and
    ``mean_outcome`` the fraction whose ``outcome`` is ``1`` (truly absent). ``gap``
    is ``abs(mean_pred - mean_outcome)``. Empty bins carry ``count = 0`` and zeroed
    statistics.
    """

    lo: float
    hi: float
    count: int
    mean_pred: float
    mean_outcome: float
    gap: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "lo": self.lo,
            "hi": self.hi,
            "count": self.count,
            "mean_pred": self.mean_pred,
            "mean_outcome": self.mean_outcome,
            "gap": self.gap,
        }


@dataclass(frozen=True)
class CalibrationReport:
    """Aggregate probability-calibration quality for absence predictions (§25.15).

    ``n`` is the number of scored rows; ``ece``/``brier`` the calibration metrics;
    ``bins`` the full ordered list of :class:`ReliabilityBin` (including empty ones)
    for reliability-diagram rendering.
    """

    bins: list[ReliabilityBin]
    ece: float
    brier: float
    n: int

    def as_dict(self) -> dict[str, object]:
        return {
            "bins": [b.as_dict() for b in self.bins],
            "ece": self.ece,
            "brier": self.brier,
            "n": self.n,
        }


def _p(row: dict) -> float:
    """Extract the predicted probability ``p`` from ``row`` as a float."""
    return float(row["p"])


def _outcome(row: dict) -> float:
    """Extract the binary ``outcome`` (0/1) from ``row`` as a float."""
    return float(row["outcome"])


def _bin_index(p: float, n_bins: int) -> int:
    """Return the bin index for probability ``p``; ``1.0`` clamps to the last bin."""
    idx = int(p * n_bins)
    if idx >= n_bins:
        idx = n_bins - 1
    if idx < 0:
        idx = 0
    return idx


def brier_score(rows: Sequence[dict]) -> float:
    """Mean squared error ``(p − outcome)²`` over ``rows`` (§25.15).

    Empty ``rows`` yields ``0.0``. So ``[{p:1, outcome:1}, {p:0, outcome:0}]`` gives
    ``0.0`` and ``[{p:0.5, outcome:1}]`` gives ``0.25``.
    """
    if not rows:
        return 0.0
    total = sum((_p(r) - _outcome(r)) ** 2 for r in rows)
    return total / len(rows)


def reliability_bins(rows: Sequence[dict], n_bins: int = 10) -> list[ReliabilityBin]:
    """Partition ``rows`` into ``n_bins`` equal-width reliability bins (§25.15).

    Each row is ``{"p": float, "outcome": 0 | 1}``. Empty bins are still returned
    with ``count = 0`` and zeroed statistics, so the list always has length
    ``n_bins``. The sum of bin counts equals ``len(rows)``. Raises ``ValueError`` on
    ``n_bins < 1``.
    """
    if n_bins < 1:
        raise ValueError(f"n_bins must be >= 1, got {n_bins}")

    counts = [0] * n_bins
    pred_sums = [0.0] * n_bins
    outcome_sums = [0.0] * n_bins
    for row in rows:
        idx = _bin_index(_p(row), n_bins)
        counts[idx] += 1
        pred_sums[idx] += _p(row)
        outcome_sums[idx] += _outcome(row)

    bins: list[ReliabilityBin] = []
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        count = counts[i]
        if count:
            mean_pred = pred_sums[i] / count
            mean_outcome = outcome_sums[i] / count
            gap = abs(mean_pred - mean_outcome)
        else:
            mean_pred = 0.0
            mean_outcome = 0.0
            gap = 0.0
        bins.append(ReliabilityBin(lo, hi, count, mean_pred, mean_outcome, gap))
    return bins


def expected_calibration_error(rows: Sequence[dict], n_bins: int = 10) -> float:
    """Weighted mean reliability gap over ``rows`` (§25.15).

    ``sum over bins of (count/N) * |mean_pred − mean_outcome|``. Empty ``rows`` (and
    thus every empty bin) contributes ``0.0``, so perfectly-calibrated rows — where
    ``mean_pred == mean_outcome`` in every non-empty bin — yield ``0.0``.
    """
    n = len(rows)
    if n == 0:
        return 0.0
    bins = reliability_bins(rows, n_bins)
    return sum((b.count / n) * b.gap for b in bins)


def analyze(rows: Sequence[dict], n_bins: int = 10) -> CalibrationReport:
    """Build a full :class:`CalibrationReport` over ``rows`` (§25.15).

    Bundles the reliability bins, ECE and Brier score with ``n = len(rows)``. Empty
    ``rows`` yields ``ece = 0.0``, ``brier = 0.0`` и ``n = 0``.
    """
    return CalibrationReport(
        bins=reliability_bins(rows, n_bins),
        ece=expected_calibration_error(rows, n_bins),
        brier=brier_score(rows),
        n=len(rows),
    )

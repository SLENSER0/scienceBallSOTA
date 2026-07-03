"""Confidence calibration + uncertainty model (§23.25).

Pure-stdlib scoring of how well a model's *predicted confidence* matches its
*empirical accuracy*. Given ``(predicted_confidence, actual_label)`` pairs — where
confidence is a probability in ``[0.0, 1.0]`` and the label is the boolean outcome —
we partition predictions into equal-width reliability bins and derive:

* **ECE** (expected calibration error) — sum over non-empty bins of the
  ``count/n``-weighted gap ``|accuracy − avg_confidence|`` (§23.25: средняя
  калибровочная ошибка).
* **MCE** (max calibration error) — the worst single-bin gap.
* **Brier score** — mean squared error ``(confidence − label)²`` над всеми парами.

Все метрики детерминированы и не зависят от внешних библиотек. Perfect calibration
(confidence equals empirical accuracy in every bin) drives ECE и MCE к ``0.0``; a
predictor confidently wrong on every example drives them к ``1.0``.

Binning convention: equal-width bins over ``[0, 1]`` where bin ``i`` covers
``[i/n_bins, (i+1)/n_bins)``. A confidence of exactly ``1.0`` is clamped into the
last bin so no prediction is dropped. Empty bins report ``count=0`` with
``avg_confidence=0.0`` и ``accuracy=0.0``. Empty input is a caller bug and raises
``ValueError`` rather than returning a vacuous report.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Bin:
    """One equal-width reliability bin over ``[0, 1]`` (§23.25).

    ``lo``/``hi`` are the bin's confidence bounds; ``count`` is the number of
    predictions that fell into it; ``avg_confidence`` is their mean predicted
    confidence and ``accuracy`` the fraction whose label is ``True``. Empty bins
    carry ``count=0`` and zeroed statistics.
    """

    lo: float
    hi: float
    count: int
    avg_confidence: float
    accuracy: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "lo": self.lo,
            "hi": self.hi,
            "count": self.count,
            "avg_confidence": self.avg_confidence,
            "accuracy": self.accuracy,
        }


@dataclass(frozen=True)
class CalibrationReport:
    """Aggregate calibration quality for a set of predictions (§23.25).

    ``n`` is the number of scored pairs, ``n_bins`` the reliability-bin count, and
    ``ece``/``mce``/``brier`` the calibration metrics. ``bins`` is the full ordered
    tuple of :class:`Bin` (including empty ones) for reliability-diagram rendering.
    """

    n: int
    n_bins: int
    ece: float
    mce: float
    brier: float
    bins: tuple[Bin, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "n": self.n,
            "n_bins": self.n_bins,
            "ece": self.ece,
            "mce": self.mce,
            "brier": self.brier,
            "bins": [b.as_dict() for b in self.bins],
        }


def _bin_index(confidence: float, n_bins: int) -> int:
    """Return the bin index for ``confidence``; ``1.0`` clamps to the last bin."""
    idx = int(confidence * n_bins)
    if idx >= n_bins:
        idx = n_bins - 1
    if idx < 0:
        idx = 0
    return idx


def reliability_bins(pairs: Sequence[tuple[float, bool]], n_bins: int = 10) -> tuple[Bin, ...]:
    """Partition ``pairs`` into ``n_bins`` equal-width reliability bins (§23.25).

    Each pair is ``(predicted_confidence, actual_label)``. Empty bins are still
    returned with ``count=0`` and zeroed statistics, so the tuple always has length
    ``n_bins``. Raises ``ValueError`` on empty input or ``n_bins < 1``.
    """
    if not pairs:
        raise ValueError("reliability_bins requires at least one (confidence, label) pair")
    if n_bins < 1:
        raise ValueError(f"n_bins must be >= 1, got {n_bins}")

    counts = [0] * n_bins
    conf_sums = [0.0] * n_bins
    hit_sums = [0] * n_bins
    for confidence, label in pairs:
        idx = _bin_index(confidence, n_bins)
        counts[idx] += 1
        conf_sums[idx] += confidence
        hit_sums[idx] += 1 if label else 0

    bins: list[Bin] = []
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        count = counts[i]
        if count:
            avg_confidence = conf_sums[i] / count
            accuracy = hit_sums[i] / count
        else:
            avg_confidence = 0.0
            accuracy = 0.0
        bins.append(Bin(lo, hi, count, avg_confidence, accuracy))
    return tuple(bins)


def expected_calibration_error(pairs: Sequence[tuple[float, bool]], n_bins: int = 10) -> float:
    """Weighted mean bin gap ``Σ (count/n)·|accuracy − avg_confidence|`` (§23.25)."""
    bins = reliability_bins(pairs, n_bins)
    n = len(pairs)
    return sum((b.count / n) * abs(b.accuracy - b.avg_confidence) for b in bins if b.count)


def max_calibration_error(pairs: Sequence[tuple[float, bool]], n_bins: int = 10) -> float:
    """Largest single-bin gap ``max |accuracy − avg_confidence|`` (§23.25)."""
    bins = reliability_bins(pairs, n_bins)
    gaps = [abs(b.accuracy - b.avg_confidence) for b in bins if b.count]
    return max(gaps) if gaps else 0.0


def brier_score(pairs: Sequence[tuple[float, bool]]) -> float:
    """Mean squared error ``(confidence − label)²`` over all pairs (§23.25)."""
    if not pairs:
        raise ValueError("brier_score requires at least one (confidence, label) pair")
    total = 0.0
    for confidence, label in pairs:
        target = 1.0 if label else 0.0
        total += (confidence - target) ** 2
    return total / len(pairs)


def calibration_report(pairs: Sequence[tuple[float, bool]], n_bins: int = 10) -> CalibrationReport:
    """Build a full :class:`CalibrationReport` (ECE + MCE + Brier + bins) (§23.25).

    Raises ``ValueError`` on empty input.
    """
    if not pairs:
        raise ValueError("calibration_report requires at least one (confidence, label) pair")
    bins = reliability_bins(pairs, n_bins)
    n = len(pairs)
    ece = sum((b.count / n) * abs(b.accuracy - b.avg_confidence) for b in bins if b.count)
    gaps = [abs(b.accuracy - b.avg_confidence) for b in bins if b.count]
    mce = max(gaps) if gaps else 0.0
    brier = brier_score(pairs)
    return CalibrationReport(n=n, n_bins=n_bins, ece=ece, mce=mce, brier=brier, bins=bins)

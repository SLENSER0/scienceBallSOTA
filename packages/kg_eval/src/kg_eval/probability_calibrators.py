"""Post-hoc confidence calibrators — histogram binning & isotonic (§18.8).

Deterministic remapping of *raw* model confidences onto *empirical* accuracies.
This complements the measurement-only :mod:`kg_eval.calibration_ece` (which reports
how badly a predictor is miscalibrated) by producing a concrete transform that
*fixes* the miscalibration: a learned ``confidence → accuracy`` map fitted from
``(confidence, label)`` pairs.

Two classic recipes, both parameter-free apart from ``n_bins``:

* **Histogram binning** — partition ``[0, 1]`` into ``n_bins`` equal-width bins and
  map every confidence in a bin to that bin's empirical positive rate (§18.8:
  гистограммная калибровка по эмпирической частоте).
* **Isotonic regression** — sort points by confidence and run Pool-Adjacent-Violators
  (PAV) to fit a nondecreasing step function (§18.8: изотоническая регрессия, PAV).

Both produce a :class:`CalibrationMap` of ``(confidence, calibrated)`` knots. ``apply``
clamps its input to ``[0, 1]`` and its output to ``[0, 1]``. Empty input is a caller
bug and raises ``ValueError`` rather than returning an identity map.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

_Pair = tuple[float, bool]
_Knot = tuple[float, float]


@dataclass(frozen=True)
class CalibrationMap:
    """A fitted ``confidence → calibrated-probability`` transform (§18.8).

    ``kind`` names the recipe (``"histogram_binning"`` или ``"isotonic"``). ``knots``
    are ``(confidence, calibrated)`` breakpoints sorted by confidence; ``apply``
    performs a piecewise-constant lookup (histogram) or step lookup (isotonic) and
    clamps the result to ``[0, 1]``.
    """

    kind: str
    knots: tuple[_Knot, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "knots": [list(knot) for knot in self.knots],
        }

    def apply(self, conf: float) -> float:
        """Map a raw ``conf`` to its calibrated probability, clamped to ``[0, 1]``.

        The input is clamped to ``[0, 1]`` first, then matched to the knot whose
        confidence is the largest not exceeding it (a right-continuous step). Below
        the first knot we return the first knot's value; above the last, the last.
        """
        if not self.knots:  # pragma: no cover - constructors never emit empty knots
            return 0.0
        x = _clamp01(conf)
        value = self.knots[0][1]
        for knot_conf, knot_val in self.knots:
            if knot_conf <= x:
                value = knot_val
            else:
                break
        return _clamp01(value)


def _clamp01(value: float) -> float:
    """Clamp ``value`` into the closed unit interval ``[0, 1]``."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def fit_histogram_binning(pairs: Sequence[_Pair], n_bins: int = 10) -> CalibrationMap:
    """Fit a histogram-binning calibrator over ``n_bins`` equal-width bins (§18.8).

    Each bin ``i`` covers ``[i/n_bins, (i+1)/n_bins)`` (the point ``1.0`` folds into
    the last bin). A bin's calibrated value is the empirical positive rate of the
    pairs that fell into it; empty bins map to ``0.0``. One knot is emitted per bin,
    keyed on the bin's lower edge, so ``apply`` performs a piecewise-constant lookup.
    """
    if not pairs:
        raise ValueError("fit_histogram_binning requires at least one (conf, label) pair")
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")

    totals = [0] * n_bins
    positives = [0] * n_bins
    for conf, label in pairs:
        idx = _bin_index(_clamp01(conf), n_bins)
        totals[idx] += 1
        if label:
            positives[idx] += 1

    knots: list[_Knot] = []
    for i in range(n_bins):
        lo = i / n_bins
        rate = positives[i] / totals[i] if totals[i] else 0.0
        knots.append((lo, rate))
    return CalibrationMap(kind="histogram_binning", knots=tuple(knots))


def _bin_index(conf: float, n_bins: int) -> int:
    """Return the equal-width bin index for ``conf`` in ``[0, 1]`` (last bin holds 1.0)."""
    idx = int(conf * n_bins)
    if idx >= n_bins:
        idx = n_bins - 1
    return idx


def fit_isotonic(pairs: Sequence[_Pair]) -> CalibrationMap:
    """Fit an isotonic (nondecreasing) calibrator via Pool-Adjacent-Violators (§18.8).

    Points are sorted by confidence, ties broken by input order, and their boolean
    labels (as ``0.0``/``1.0``) are fed to PAV. The algorithm merges adjacent blocks
    that violate monotonicity into weighted-mean pools, yielding a nondecreasing
    fitted value per original point. One knot is emitted per point.
    """
    if not pairs:
        raise ValueError("fit_isotonic requires at least one (conf, label) pair")

    ordered = sorted(range(len(pairs)), key=lambda i: pairs[i][0])
    confs = [_clamp01(pairs[i][0]) for i in ordered]
    targets = [1.0 if pairs[i][1] else 0.0 for i in ordered]

    fitted = _pav(targets)
    knots = tuple(zip(confs, fitted, strict=True))
    return CalibrationMap(kind="isotonic", knots=knots)


def _pav(targets: Sequence[float]) -> list[float]:
    """Pool-Adjacent-Violators: least-squares nondecreasing fit of ``targets``.

    Maintains a stack of ``(sum, weight)`` blocks; whenever a new value would break
    monotonicity it is merged with the preceding block, cascading merges until the
    block means are nondecreasing. Returns the per-index fitted values.
    """
    sums: list[float] = []
    weights: list[float] = []
    counts: list[int] = []
    for value in targets:
        sums.append(value)
        weights.append(1.0)
        counts.append(1)
        while len(sums) > 1 and sums[-2] / weights[-2] > sums[-1] / weights[-1]:
            s = sums.pop() + sums[-1]
            w = weights.pop() + weights[-1]
            c = counts.pop() + counts[-1]
            sums[-1], weights[-1], counts[-1] = s, w, c

    fitted: list[float] = []
    for s, w, c in zip(sums, weights, counts, strict=True):
        fitted.extend([s / w] * c)
    return fitted

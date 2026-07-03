"""Single-metric bootstrap confidence interval (§18.11).

Reporting/significance helper: given a single sample of per-item metric values
(e.g. per-query recall), estimate a percentile-bootstrap confidence interval
around a plug-in ``statistic`` (default: the mean). Unlike
``paired_bootstrap.paired_bootstrap`` — which compares *two* systems' paired
scores — this reports one metric's uncertainty for headline numbers.

Детерминизм обязателен: ``random.Random(seed)`` даёт одинаковые границы CI при
одинаковом ``seed``, чтобы отчёт был воспроизводим в CI (§18.11: отчётность и
значимость — доверительный интервал одной метрики через bootstrap).
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean of a non-empty sequence."""
    return sum(values) / len(values)


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated ``q``-quantile (``q`` in ``[0, 1]``) of sorted data."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


@dataclass(frozen=True)
class BootstrapCI:
    """Percentile-bootstrap confidence interval for one metric.

    ``point`` is the plug-in ``statistic`` on the observed sample;
    ``lower``/``upper`` bracket it at the requested ``confidence`` level, taken
    as the ``(1-confidence)/2`` and ``(1+confidence)/2`` percentiles of the
    resample statistics. ``n`` is the sample size, ``n_resamples`` the number of
    bootstrap replicates drawn.
    """

    n: int
    point: float
    lower: float
    upper: float
    confidence: float
    n_resamples: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n": self.n,
            "point": round(self.point, 6),
            "lower": round(self.lower, 6),
            "upper": round(self.upper, 6),
            "confidence": self.confidence,
            "n_resamples": self.n_resamples,
        }


def bootstrap_ci(
    sample: Sequence[float],
    *,
    confidence: float = 0.95,
    n_resamples: int = 2000,
    seed: int = 0,
    statistic: Callable[[Sequence[float]], float] = mean,
) -> BootstrapCI:
    """Percentile-bootstrap confidence interval for a single-metric ``sample``.

    Draws ``n_resamples`` samples of size ``len(sample)`` with replacement using
    ``random.Random(seed)``, applies ``statistic`` to each, and returns the
    ``(1-confidence)/2`` / ``(1+confidence)/2`` percentiles as ``lower`` /
    ``upper`` around the plug-in ``point = statistic(sample)``. Bounds are
    clamped so ``lower <= point <= upper`` even under skew/rounding.

    Raises ``ValueError`` on empty ``sample``, ``confidence`` outside ``(0, 1)``,
    or non-positive ``n_resamples``.
    """
    n = len(sample)
    if n == 0:
        raise ValueError("sample must be non-empty")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in the open interval (0, 1)")
    if n_resamples <= 0:
        raise ValueError("n_resamples must be positive")

    data = [float(x) for x in sample]
    point = float(statistic(data))

    rng = random.Random(seed)
    stats: list[float] = []
    for _ in range(n_resamples):
        resample = [data[rng.randrange(n)] for _ in range(n)]
        stats.append(float(statistic(resample)))

    stats.sort()
    tail = (1.0 - confidence) / 2.0
    lower = _percentile(stats, tail)
    upper = _percentile(stats, 1.0 - tail)
    # Guarantee lower <= point <= upper even under skew/rounding.
    lower = min(lower, point)
    upper = max(upper, point)

    return BootstrapCI(
        n=n,
        point=point,
        lower=lower,
        upper=upper,
        confidence=confidence,
        n_resamples=n_resamples,
    )

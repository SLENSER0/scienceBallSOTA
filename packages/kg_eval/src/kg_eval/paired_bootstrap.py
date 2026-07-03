"""Paired significance testing for baseline/ablation benchmarks (§23.31).

Pure-stdlib, deterministic paired significance testing of two systems'
per-query scores, to justify "statistically better than baseline" claims.
``retrieval_metrics.recall_wilson_ci`` only gives a single-proportion CI — it
cannot say whether *system* beats *baseline*, so this module adds a paired
bootstrap over per-query score differences plus a McNemar discordant-pair
count for correct/incorrect flags (§23.31: обосновать «значимо лучше базовой
линии» для ablation-сравнений).

Детерминизм — краеугольный камень: ``random.Random(seed)`` даёт одинаковый
``p_value`` при одинаковом ``seed``, чтобы бенчмарк был воспроизводим в CI.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SignificanceResult:
    """Outcome of a paired bootstrap comparison of two systems.

    ``mean_diff`` is ``mean(system[i] - baseline[i])`` — positive means the
    system scores higher on average. ``ci_low``/``ci_high`` bracket the mean
    difference; ``significant`` is ``p_value < alpha``.
    """

    n: int
    mean_diff: float
    p_value: float
    ci_low: float
    ci_high: float
    significant: bool

    def as_dict(self) -> dict[str, float | int | bool]:
        return {
            "n": self.n,
            "mean_diff": round(self.mean_diff, 6),
            "p_value": round(self.p_value, 6),
            "ci_low": round(self.ci_low, 6),
            "ci_high": round(self.ci_high, 6),
            "significant": self.significant,
        }


def _mean(values: Sequence[float]) -> float:
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


def paired_bootstrap(
    baseline: Sequence[float],
    system: Sequence[float],
    *,
    iterations: int = 1000,
    seed: int = 0,
    alpha: float = 0.05,
) -> SignificanceResult:
    """Paired bootstrap significance test of ``system`` vs ``baseline``.

    Resamples the per-query differences ``system[i] - baseline[i]`` with
    replacement ``iterations`` times using ``random.Random(seed)``. The
    two-sided ``p_value`` is ``2 * min(frac_le, frac_ge)`` where ``frac_le`` /
    ``frac_ge`` are the fractions of resample means ``<= 0`` / ``>= 0`` (capped
    at ``1.0``). Result is ``significant`` when ``p_value < alpha``.

    Raises ``ValueError`` on length mismatch or empty input.
    """
    if len(baseline) != len(system):
        raise ValueError("baseline and system must have equal length")
    n = len(baseline)
    if n == 0:
        raise ValueError("inputs must be non-empty")
    if iterations <= 0:
        raise ValueError("iterations must be positive")

    diffs = [float(s) - float(b) for b, s in zip(baseline, system)]  # noqa: B905
    mean_diff = _mean(diffs)

    rng = random.Random(seed)
    resample_means: list[float] = []
    for _ in range(iterations):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        resample_means.append(_mean(sample))

    le = sum(1 for m in resample_means if m <= 0.0) / iterations
    ge = sum(1 for m in resample_means if m >= 0.0) / iterations
    p_value = min(1.0, 2.0 * min(le, ge))

    resample_means.sort()
    ci_low = _percentile(resample_means, alpha / 2.0)
    ci_high = _percentile(resample_means, 1.0 - alpha / 2.0)
    # Guarantee ci_low <= mean_diff <= ci_high even under skew/rounding.
    ci_low = min(ci_low, mean_diff)
    ci_high = max(ci_high, mean_diff)

    return SignificanceResult(
        n=n,
        mean_diff=mean_diff,
        p_value=p_value,
        ci_low=ci_low,
        ci_high=ci_high,
        significant=p_value < alpha,
    )


def mcnemar(
    baseline_correct: Sequence[bool],
    system_correct: Sequence[bool],
) -> tuple[int, int]:
    """Discordant-pair counts ``(b, c)`` for a McNemar test.

    ``b`` counts queries the baseline got right but the system got wrong; ``c``
    counts the inverse (system right, baseline wrong). Concordant pairs (both
    right / both wrong) are ignored. Raises ``ValueError`` on length mismatch.
    """
    if len(baseline_correct) != len(system_correct):
        raise ValueError("baseline_correct and system_correct must have equal length")
    b = sum(1 for bc, sc in zip(baseline_correct, system_correct) if bc and not sc)  # noqa: B905
    c = sum(1 for bc, sc in zip(baseline_correct, system_correct) if sc and not bc)  # noqa: B905
    return b, c

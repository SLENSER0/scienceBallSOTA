"""Effect-size measures for benchmark comparisons (§23.31).

``paired_bootstrap`` answers *whether* a system beats a baseline (p-value/CI),
but a significant p-value on a large sample can hide a trivially small gain. To
support the §23.31 «statistically better» acceptance criterion we also need to
quantify *how much* better — the magnitude of the effect, not just its sign.

This module adds two standard, pure-stdlib effect-size statistics:

* **Cohen's d** — standardised mean difference (mean gap over pooled std).
* **Cliff's delta** — non-parametric dominance: the fraction of pairs where the
  system wins minus the fraction where it loses, bounded in ``[-1, 1]``.

Cliff's delta шкалируется по общепринятым порогам (Romano et al.): |δ| < 0.147
«negligible», < 0.33 «small», < 0.474 «medium», иначе «large» — так бенчмарк
может отличить «значимо, но мизерно» от «значимо и существенно».
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# Romano et al. (2006) thresholds on |Cliff's delta| → qualitative magnitude.
_NEGLIGIBLE = 0.147
_SMALL = 0.33
_MEDIUM = 0.474


@dataclass(frozen=True)
class EffectSize:
    """Magnitude of a system-vs-baseline benchmark difference.

    ``cohens_d`` — standardised mean difference (positive: system higher).
    ``cliffs_delta`` — dominance in ``[-1, 1]`` (positive: system dominates).
    ``magnitude`` — qualitative bucket of ``abs(cliffs_delta)``.
    """

    cohens_d: float
    cliffs_delta: float
    magnitude: str

    def as_dict(self) -> dict[str, float | str]:
        return {
            "cohens_d": round(self.cohens_d, 6),
            "cliffs_delta": round(self.cliffs_delta, 6),
            "magnitude": self.magnitude,
        }


def _mean(values: Sequence[float]) -> float:
    """Arithmetic mean of a non-empty sequence."""
    return sum(values) / len(values)


def _sample_variance(values: Sequence[float], mean: float) -> float:
    """Unbiased (``ddof=1``) sample variance; ``0.0`` for a single value."""
    n = len(values)
    if n < 2:
        return 0.0
    return sum((v - mean) ** 2 for v in values) / (n - 1)


def _require_nonempty(system: Sequence[float], baseline: Sequence[float]) -> None:
    """Пустой ``system`` или ``baseline`` → ValueError (нечего сравнивать)."""
    if len(system) == 0 or len(baseline) == 0:
        raise ValueError("system and baseline must both be non-empty")


def cohens_d(system: Sequence[float], baseline: Sequence[float]) -> float:
    """Cohen's d: (mean(system) - mean(baseline)) over the pooled std.

    Uses the pooled sample standard deviation with ``ddof=1``. When the pooled
    std is ``0`` (no variance in either group) the effect is defined as ``0.0``.
    """
    _require_nonempty(system, baseline)
    n1, n2 = len(system), len(baseline)
    m1, m2 = _mean(system), _mean(baseline)
    var1, var2 = _sample_variance(system, m1), _sample_variance(baseline, m2)
    dof = n1 + n2 - 2
    pooled_var = 0.0 if dof <= 0 else ((n1 - 1) * var1 + (n2 - 1) * var2) / dof
    pooled_std = pooled_var**0.5
    if pooled_std == 0.0:
        return 0.0
    return (m1 - m2) / pooled_std


def cliffs_delta(system: Sequence[float], baseline: Sequence[float]) -> float:
    """Cliff's delta: fraction of pairs system>baseline minus system<baseline.

    Compares every ``(s, b)`` pair; result is bounded in ``[-1, 1]``. ``+1``
    means the system beats the baseline on every pair, ``-1`` the opposite.
    """
    _require_nonempty(system, baseline)
    greater = 0
    less = 0
    for s in system:
        for b in baseline:
            if s > b:
                greater += 1
            elif s < b:
                less += 1
    total = len(system) * len(baseline)
    return (greater - less) / total


def _magnitude(delta: float) -> str:
    """Bucket ``abs(delta)`` into a qualitative magnitude label."""
    d = abs(delta)
    if d < _NEGLIGIBLE:
        return "negligible"
    if d < _SMALL:
        return "small"
    if d < _MEDIUM:
        return "medium"
    return "large"


def analyze(system: Sequence[float], baseline: Sequence[float]) -> EffectSize:
    """Compute both effect sizes and the qualitative magnitude bucket."""
    _require_nonempty(system, baseline)
    d = cohens_d(system, baseline)
    delta = cliffs_delta(system, baseline)
    return EffectSize(cohens_d=d, cliffs_delta=delta, magnitude=_magnitude(delta))

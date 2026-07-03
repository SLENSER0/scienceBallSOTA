"""Wilson score confidence interval on a recall proportion (§25.19).

Доверительный интервал Уилсона — a recall metric like ``successes/n`` is a point
estimate of a Bernoulli success rate, and reporting it without an interval hides how
much sampling noise it carries. The Wilson score interval is the standard small-sample
CI for a binomial proportion: unlike the naive normal (Wald) interval it stays inside
``[0, 1]``, does not collapse to zero width at ``p == 0`` or ``p == 1``, and behaves
well for small ``n`` — exactly the regime a retrieval-recall audit runs in.

This module is pure arithmetic: no graph, no I/O. Callers pass the number of relevant
items retrieved (``successes``) and the number scored (``n``) and receive a frozen
:class:`WilsonInterval` describing the point estimate and its lower/upper bounds.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

# Default z-score: 1.96 -> two-sided 95% confidence (§25.19).
_DEFAULT_Z = 1.96


@dataclass(frozen=True)
class WilsonInterval:
    """Wilson score interval for a recall proportion (интервал Уилсона).

    Attributes:
        point: наблюдаемая доля — observed proportion ``successes/n`` (``0.0`` if ``n == 0``).
        lower: lower bound of the interval, clamped to ``>= 0``.
        upper: upper bound of the interval, clamped to ``<= 1``.
        n: sample size the interval was computed over.
        z: z-score (standard-normal quantile) used for the bound.
        width: ``upper - lower`` — the interval's total span.
    """

    point: float
    lower: float
    upper: float
    n: int
    z: float
    width: float

    def as_dict(self) -> dict[str, float | int]:
        """Return a plain dict with floats rounded to 4 decimals (``n`` kept exact)."""
        return {
            "point": round(self.point, 4),
            "lower": round(self.lower, 4),
            "upper": round(self.upper, 4),
            "n": self.n,
            "z": round(self.z, 4),
            "width": round(self.width, 4),
        }


def wilson_interval(successes: int, n: int, *, z: float = _DEFAULT_Z) -> WilsonInterval:
    """Compute the Wilson score interval for ``successes`` out of ``n`` (§25.19).

    Формула Уилсона: with ``p = successes / n`` the interval is centred at
    ``(p + z^2 / 2n) / (1 + z^2 / n)`` with half-width
    ``z / (1 + z^2 / n) * sqrt(p(1-p)/n + z^2 / 4n^2)``. Bounds are clamped into
    ``[0, 1]``. When ``n == 0`` the estimate is undefined, so we return the maximally
    uninformative ``point=0.0``, ``lower=0.0``, ``upper=1.0`` (``width=1.0``).

    Args:
        successes: number of relevant items retrieved (``0 <= successes <= n``).
        n: number of items scored.
        z: standard-normal quantile; defaults to ``1.96`` (95% two-sided).

    Returns:
        A frozen :class:`WilsonInterval`.
    """
    if n == 0:
        return WilsonInterval(point=0.0, lower=0.0, upper=1.0, n=0, z=z, width=1.0)

    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = (z / denom) * sqrt(p * (1.0 - p) / n + z2 / (4 * n * n))

    lower = max(0.0, center - half)
    upper = min(1.0, center + half)
    return WilsonInterval(point=p, lower=lower, upper=upper, n=n, z=z, width=upper - lower)

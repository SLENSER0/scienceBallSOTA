"""Exact paired permutation (sign-flip) significance test (§18.11).

A paired randomization test on per-query score differences. When the number
of pairs is small (``n <= max_exact``) we *enumerate* all ``2 ** n`` sign
assignments to compute an exact two-sided ``p``-value; otherwise we fall back
to ``n_resamples`` seeded random sign-flips (a Monte-Carlo approximation).

Unlike ``paired_bootstrap`` (which resamples *with replacement*), the sign-flip
test is the natural exact test for the paired null "the two systems are
exchangeable", giving hand-checkable ``p``-values on tiny inputs (§18.11:
точный парный permutation-тест для обоснования значимости).

Детерминизм — краеугольный камень: точный путь не зависит от seed, а
выборочный путь через ``random.Random(seed)`` даёт одинаковый ``p_value``
при одинаковом ``seed`` для воспроизводимости в CI.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class PermutationResult:
    """Outcome of a paired sign-flip permutation test.

    ``observed_diff`` is ``mean(system[i] - baseline[i])`` — positive means the
    system scores higher on average. ``p_value`` is the two-sided fraction of
    sign-flip permutations whose ``|mean|`` is ``>=`` the observed ``|mean|``
    (inclusive). ``exact`` is ``True`` when all ``2 ** n`` flips were
    enumerated; ``n_resamples`` is the number of permutations actually
    evaluated (``2 ** n`` on the exact path).
    """

    n: int
    observed_diff: float
    p_value: float
    exact: bool
    n_resamples: int

    def as_dict(self) -> dict[str, float | int | bool]:
        return {
            "n": self.n,
            "observed_diff": round(self.observed_diff, 6),
            "p_value": round(self.p_value, 6),
            "exact": self.exact,
            "n_resamples": self.n_resamples,
        }


def _mean(values: Sequence[float]) -> float:
    """Arithmetic mean of a non-empty sequence."""
    return sum(values) / len(values)


def _exact_p(diffs: Sequence[float], observed_abs: float) -> tuple[float, int]:
    """Enumerate all ``2 ** n`` sign-flips; return ``(p_value, n_flips)``.

    Counts permutations whose absolute mean is ``>= observed_abs`` (inclusive)
    and divides by the total ``2 ** n`` assignments.
    """
    n = len(diffs)
    total = 1 << n  # 2 ** n
    hits = 0
    # Небольшая числовая поблажка, чтобы observed-перестановка всегда попадала.
    eps = 1e-12
    for mask in range(total):
        acc = 0.0
        for i, d in enumerate(diffs):
            acc += d if (mask >> i) & 1 else -d
        if abs(acc / n) >= observed_abs - eps:
            hits += 1
    return hits / total, total


def _sampled_p(
    diffs: Sequence[float],
    observed_abs: float,
    n_resamples: int,
    seed: int,
) -> float:
    """Monte-Carlo sign-flip ``p``-value using ``random.Random(seed)``.

    Draws ``n_resamples`` independent random sign vectors and returns the
    inclusive fraction whose absolute permuted mean is ``>= observed_abs``.
    """
    n = len(diffs)
    rng = random.Random(seed)
    eps = 1e-12
    hits = 0
    for _ in range(n_resamples):
        acc = 0.0
        for d in diffs:
            acc += d if rng.random() < 0.5 else -d
        if abs(acc / n) >= observed_abs - eps:
            hits += 1
    return hits / n_resamples


def paired_permutation(
    system: Sequence[float],
    baseline: Sequence[float],
    *,
    max_exact: int = 20,
    n_resamples: int = 10000,
    seed: int = 0,
) -> PermutationResult:
    """Paired sign-flip permutation test of ``system`` vs ``baseline``.

    Computes per-pair differences ``system[i] - baseline[i]`` and their mean
    (``observed_diff``). Under the exchangeability null, each difference could
    equally have had its sign flipped. When ``n <= max_exact`` all ``2 ** n``
    sign assignments are enumerated (``exact=True``, ``n_resamples == 2 ** n``);
    otherwise ``n_resamples`` seeded random flips approximate the distribution.

    The two-sided ``p_value`` is the inclusive fraction of permutations whose
    ``|permuted mean| >= |observed mean|``.

    Raises ``ValueError`` on length mismatch or empty input.
    """
    if len(system) != len(baseline):
        raise ValueError("system and baseline must have equal length")
    n = len(system)
    if n == 0:
        raise ValueError("inputs must be non-empty")
    if n_resamples <= 0:
        raise ValueError("n_resamples must be positive")

    diffs = [float(s) - float(b) for s, b in zip(system, baseline)]  # noqa: B905
    observed_diff = _mean(diffs)
    observed_abs = abs(observed_diff)

    if n <= max_exact:
        p_value, n_flips = _exact_p(diffs, observed_abs)
        return PermutationResult(
            n=n,
            observed_diff=observed_diff,
            p_value=p_value,
            exact=True,
            n_resamples=n_flips,
        )

    p_value = _sampled_p(diffs, observed_abs, n_resamples, seed)
    return PermutationResult(
        n=n,
        observed_diff=observed_diff,
        p_value=p_value,
        exact=False,
        n_resamples=n_resamples,
    )

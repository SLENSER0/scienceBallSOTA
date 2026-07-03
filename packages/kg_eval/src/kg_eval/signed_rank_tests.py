"""Nonparametric paired significance tests (§18.11).

``paired_bootstrap`` resamples to get a p-value, but on small paired benchmark
runs (a handful of shared questions) resampling is noisy and its Gaussian-ish
assumptions are shaky. Two classical distribution-free paired tests are more
appropriate there and need no external SciPy dependency:

* **Wilcoxon signed-rank** — ranks the *magnitudes* of the nonzero paired
  differences, then sums the ranks of the positive (``W+``) and negative
  (``W-``) differences. Ties in ``|d|`` share the *average* rank; exact zero
  differences are dropped (Wilcoxon's original convention).
* **Sign test** — ignores magnitudes entirely and asks only how many pairs
  moved up vs down, scored against an exact ``Binomial(n, 0.5)`` two-sided
  tail. Maximally robust, minimally powerful.

Оба теста парные: ``system[i]`` и ``baseline[i]`` — один и тот же пример,
поэтому длины последовательностей обязаны совпадать (иначе ValueError).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import comb


@dataclass(frozen=True)
class PairedTestResult:
    """Combined Wilcoxon signed-rank + sign-test outcome for a paired run.

    ``n`` — total pairs; ``n_nonzero`` — pairs with a nonzero difference.
    ``w_plus`` / ``w_minus`` — Wilcoxon rank sums for positive / negative diffs.
    ``statistic`` — ``min(w_plus, w_minus)`` (the usual Wilcoxon test stat).
    ``sign_pos`` / ``sign_neg`` — counts of upward / downward moves.
    ``sign_p_two_sided`` — exact two-sided binomial p under ``p = 0.5``.
    """

    n: int
    n_nonzero: int
    w_plus: float
    w_minus: float
    statistic: float
    sign_pos: int
    sign_neg: int
    sign_p_two_sided: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n": self.n,
            "n_nonzero": self.n_nonzero,
            "w_plus": round(self.w_plus, 6),
            "w_minus": round(self.w_minus, 6),
            "statistic": round(self.statistic, 6),
            "sign_pos": self.sign_pos,
            "sign_neg": self.sign_neg,
            "sign_p_two_sided": round(self.sign_p_two_sided, 6),
        }


def _require_equal_length(system: Sequence[float], baseline: Sequence[float]) -> None:
    """Разная длина ``system`` / ``baseline`` → ValueError (пары не сходятся)."""
    if len(system) != len(baseline):
        raise ValueError(
            f"system and baseline must be the same length: {len(system)} != {len(baseline)}"
        )


def _differences(system: Sequence[float], baseline: Sequence[float]) -> list[float]:
    """Paired differences ``system[i] - baseline[i]`` over aligned pairs."""
    return [float(s) - float(b) for s, b in zip(system, baseline, strict=True)]


def _average_ranks(magnitudes: Sequence[float]) -> list[float]:
    """Average (fractional) ranks of ``magnitudes``, ties sharing their mean rank.

    Ranks start at ``1``. A group of ``k`` equal values spanning positions
    ``p..p+k-1`` (1-based) each receive ``(p + (p+k-1)) / 2``.
    """
    order = sorted(range(len(magnitudes)), key=lambda i: magnitudes[i])
    ranks = [0.0] * len(magnitudes)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and magnitudes[order[j + 1]] == magnitudes[order[i]]:
            j += 1
        # positions i..j (0-based) → 1-based ranks (i+1)..(j+1); average them.
        avg = ((i + 1) + (j + 1)) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def wilcoxon_signed_rank(system: Sequence[float], baseline: Sequence[float]) -> tuple[float, float]:
    """Wilcoxon signed-rank sums ``(W+, W-)`` over nonzero paired differences.

    Zero differences are dropped; the remaining ``|d|`` are average-ranked and
    each rank is added to ``W+`` (if ``d > 0``) or ``W-`` (if ``d < 0``).
    """
    _require_equal_length(system, baseline)
    diffs = [d for d in _differences(system, baseline) if d != 0.0]
    if not diffs:
        return (0.0, 0.0)
    ranks = _average_ranks([abs(d) for d in diffs])
    w_plus = sum(r for d, r in zip(diffs, ranks, strict=True) if d > 0)
    w_minus = sum(r for d, r in zip(diffs, ranks, strict=True) if d < 0)
    return (w_plus, w_minus)


def _binomial_two_sided_p(pos: int, neg: int) -> float:
    """Exact two-sided ``Binomial(n, 0.5)`` p-value for ``pos``/``neg`` splits.

    ``n = pos + neg``; sums the probability of every split at least as extreme
    as ``min(pos, neg)`` in both tails. Empty (``n == 0``) → ``1.0`` (no move).
    """
    n = pos + neg
    if n == 0:
        return 1.0
    k = min(pos, neg)
    tail = sum(comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2.0 * tail)


def sign_test(system: Sequence[float], baseline: Sequence[float]) -> tuple[int, int, float]:
    """Sign test: ``(#positive, #negative, exact two-sided binomial p)``.

    Counts pairs that moved up vs down (zeros ignored) and scores the split
    against an exact ``Binomial(n_nonzero, 0.5)`` two-sided tail.
    """
    _require_equal_length(system, baseline)
    diffs = _differences(system, baseline)
    pos = sum(1 for d in diffs if d > 0)
    neg = sum(1 for d in diffs if d < 0)
    return (pos, neg, _binomial_two_sided_p(pos, neg))


def analyze(system: Sequence[float], baseline: Sequence[float]) -> PairedTestResult:
    """Run both tests over a paired run, packaged as a ``PairedTestResult``."""
    _require_equal_length(system, baseline)
    w_plus, w_minus = wilcoxon_signed_rank(system, baseline)
    pos, neg, p_two_sided = sign_test(system, baseline)
    diffs = _differences(system, baseline)
    n_nonzero = sum(1 for d in diffs if d != 0.0)
    return PairedTestResult(
        n=len(diffs),
        n_nonzero=n_nonzero,
        w_plus=w_plus,
        w_minus=w_minus,
        statistic=min(w_plus, w_minus),
        sign_pos=pos,
        sign_neg=neg,
        sign_p_two_sided=p_two_sided,
    )

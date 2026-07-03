"""Rank-correlation statistics for metric agreement (§18.11).

The §18.9 evaluation harness produces *several* scores per item — an LLM-judge
verdict, deterministic overlap metrics, model confidence — and we regularly ask
whether two of these *rank* items the same way: does the judge agree with the
deterministic metric? does higher confidence track higher correctness? Pearson
correlation answers this only for linear relationships; rank correlation is the
robust, monotone-relationship answer we want here.

This module offers two classic, pure-stdlib rank-correlation coefficients:

* **Spearman's ρ** — Pearson correlation computed on *average ranks* (ties get
  the mean of the ranks they span).
* **Kendall's τ-a** — ``(concordant - discordant) / C(n, 2)``, the net fraction
  of concordant pairs (no tie correction; τ-a variant).

Оба коэффициента лежат в ``[-1, 1]``: ``+1`` — идеально согласованный порядок,
``-1`` — полностью обратный. Используется для корреляции LLM-судьи против
детерминированных метрик (§18.9) и «уверенность против правильности».
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RankCorrelation:
    """Bundled rank-correlation result for a pair of score sequences.

    ``n`` — number of paired observations (``>= 2``).
    ``spearman_rho`` — Spearman's ρ on average ranks, in ``[-1, 1]``.
    ``kendall_tau`` — Kendall's τ-a, in ``[-1, 1]``.
    """

    n: int
    spearman_rho: float
    kendall_tau: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n": self.n,
            "spearman_rho": round(self.spearman_rho, 4),
            "kendall_tau": round(self.kendall_tau, 4),
        }


def _validate(x: Sequence[float], y: Sequence[float]) -> int:
    """Проверка входа: равные длины и ``n >= 2``; возвращает ``n``."""
    if len(x) != len(y):
        raise ValueError("x and y must have the same length")
    n = len(x)
    if n < 2:
        raise ValueError("need at least two paired observations")
    return n


def _average_ranks(values: Sequence[float]) -> list[float]:
    """Average (fractional) ranks: tied values share the mean of their ranks."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        # Ranks are 1-based; group spans positions [i, j] → shared average rank.
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def _pearson(a: Sequence[float], b: Sequence[float]) -> float:
    """Pearson correlation of two equal-length sequences; ``0.0`` if no variance."""
    n = len(a)
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
    var_a = sum((a[i] - mean_a) ** 2 for i in range(n))
    var_b = sum((b[i] - mean_b) ** 2 for i in range(n))
    denom = (var_a * var_b) ** 0.5
    if denom == 0.0:
        return 0.0
    return cov / denom


def spearman_rho(x: Sequence[float], y: Sequence[float]) -> float:
    """Spearman's ρ: Pearson correlation on the average ranks of ``x`` and ``y``.

    Length mismatch or ``n < 2`` raises ``ValueError``.
    """
    _validate(x, y)
    return _pearson(_average_ranks(x), _average_ranks(y))


def kendall_tau(x: Sequence[float], y: Sequence[float]) -> float:
    """Kendall's τ-a: ``(concordant - discordant) / C(n, 2)`` over all pairs.

    A pair ``(i, j)`` is concordant when ``x`` and ``y`` order it the same way,
    discordant when they disagree; ties contribute to neither (τ-a variant).
    Length mismatch or ``n < 2`` raises ``ValueError``.
    """
    n = _validate(x, y)
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = x[j] - x[i]
            dy = y[j] - y[i]
            sign = dx * dy
            if sign > 0:
                concordant += 1
            elif sign < 0:
                discordant += 1
    pairs = n * (n - 1) / 2
    return (concordant - discordant) / pairs


def analyze(x: Sequence[float], y: Sequence[float]) -> RankCorrelation:
    """Compute both rank correlations for the paired sequences ``x`` and ``y``."""
    n = _validate(x, y)
    return RankCorrelation(
        n=n,
        spearman_rho=spearman_rho(x, y),
        kendall_tau=kendall_tau(x, y),
    )

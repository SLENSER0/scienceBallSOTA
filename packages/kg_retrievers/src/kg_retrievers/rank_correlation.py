"""Ranking-agreement metrics for rerank / fusion impact reports (§12.11).

Метрики согласия ранжирований — quantify how much a reranker or a fusion step
reorders a candidate list relative to the pre-rerank order. A recall CI (see
``recall_wilson_ci``) tells you *how good* the top-k is; these metrics tell you
*how much the order changed*, which is what an eval trace or a reranker-impact
report needs to attribute a recall delta to the reorder itself.

Three complementary agreements are provided:

* **Kendall tau** (τ) — pairwise concordance over the items common to both lists.
  ``+1`` when every common pair keeps its relative order, ``-1`` when every pair
  flips. Insensitive to *where* in the list a swap happens.
* **Spearman rho** (ρ) — Pearson correlation of the two rank vectors over the
  common items; ``+1`` identical order, ``-1`` fully reversed.
* **RBO** (rank-biased overlap) — top-weighted set overlap in ``(0, 1]`` that does
  *not* require the two lists to share the same items and weights early ranks more
  heavily, so moving the true answer out of the top hurts more than shuffling the
  tail (Webber, Moffat & Zobel 2010, extrapolated RBO_EXT).

Pure arithmetic: no graph, no I/O. Callers pass two ordered id sequences (e.g. the
candidate ids before and after rerank) and receive a frozen
:class:`RankAgreement`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

# RBO float dust guard: the extrapolated sum is 1.0 in exact arithmetic for equal
# lists but accrues ~1e-16 rounding; round to this many places before clamping.
_RBO_ROUND = 12


@dataclass(frozen=True)
class RankAgreement:
    """Agreement between two rankings (согласие ранжирований) (§12.11).

    Attributes:
        kendall_tau: pairwise concordance τ over the common items, in ``[-1, 1]``.
        spearman_rho: rank correlation ρ over the common items, in ``[-1, 1]``.
        rbo: top-weighted rank-biased overlap in ``[0, 1]`` (``1`` = identical).
        n: number of items common to both rankings (the τ/ρ support size).
    """

    kendall_tau: float
    spearman_rho: float
    rbo: float
    n: int

    def as_dict(self) -> dict[str, float | int]:
        """Return a plain dict with all four fields (floats rounded to 6 dp)."""
        return {
            "kendall_tau": round(self.kendall_tau, 6),
            "spearman_rho": round(self.spearman_rho, 6),
            "rbo": round(self.rbo, 6),
            "n": self.n,
        }


def _common(a: Sequence[str], b: Sequence[str]) -> list[str]:
    """Return the set of items present in both ``a`` and ``b`` (order irrelevant)."""
    return sorted(set(a) & set(b))


def kendall_tau(a: Sequence[str], b: Sequence[str]) -> float:
    """Kendall τ over the items common to ``a`` and ``b`` (§12.11).

    τ = ``(C - D) / (C + D)`` where ``C``/``D`` count concordant/discordant pairs
    of common items. With distinct ids there are no ties, so ``C + D = n(n-1)/2``.
    Returns ``1.0`` when fewer than two items are shared (no pair can disagree).
    """
    common = _common(a, b)
    if len(common) < 2:
        return 1.0
    pos_a = {item: i for i, item in enumerate(a)}
    pos_b = {item: i for i, item in enumerate(b)}
    concordant = 0
    discordant = 0
    for x, y in combinations(common, 2):
        order = (pos_a[x] - pos_a[y]) * (pos_b[x] - pos_b[y])
        if order > 0:
            concordant += 1
        elif order < 0:
            discordant += 1
    total = concordant + discordant
    if total == 0:
        return 1.0
    return (concordant - discordant) / total


def spearman_rho(a: Sequence[str], b: Sequence[str]) -> float:
    """Spearman ρ over the items common to ``a`` and ``b`` (§12.11).

    ρ = ``1 - 6·Σd² / (n·(n²-1))`` where ``d`` is the difference between an item's
    1-based rank among the common items in ``a`` and its rank in ``b``. Returns
    ``1.0`` when fewer than two items are shared.
    """
    common = _common(a, b)
    n = len(common)
    if n < 2:
        return 1.0
    pos_a = {item: i for i, item in enumerate(a)}
    pos_b = {item: i for i, item in enumerate(b)}
    rank_a = {item: r for r, item in enumerate(sorted(common, key=pos_a.__getitem__), 1)}
    rank_b = {item: r for r, item in enumerate(sorted(common, key=pos_b.__getitem__), 1)}
    d2 = sum((rank_a[item] - rank_b[item]) ** 2 for item in common)
    return 1.0 - (6.0 * d2) / (n * (n * n - 1))


def rbo(a: Sequence[str], b: Sequence[str], *, p: float = 0.9) -> float:
    """Rank-biased overlap (extrapolated RBO_EXT) of ``a`` and ``b`` (§12.11).

    Top-weighted overlap in ``(0, 1]``: ``p`` sets how quickly weight decays with
    depth (``p→1`` weights the whole list evenly, small ``p`` weights only the very
    top). ``1.0`` for identical lists, ``0.0`` for disjoint lists. Unlike τ/ρ it
    needs no shared support and rewards agreement near the top far more than
    agreement in the tail (Webber, Moffat & Zobel 2010).
    """
    if not 0.0 < p < 1.0:
        raise ValueError(f"rbo persistence p must be in (0, 1), got {p!r}")
    la, lb = len(a), len(b)
    if la == 0 or lb == 0:
        return 0.0
    # Work with the shorter list as S (length s) and the longer as L (length ll).
    if la <= lb:
        short, long, s, ll = a, b, la, lb
    else:
        short, long, s, ll = b, a, lb, la
    # X[d-1] = |top-d(short) ∩ top-d(long)|, short prefix capped at its length s.
    seen_short: set[str] = set()
    seen_long: set[str] = set()
    x: list[int] = []
    for d in range(1, ll + 1):
        if d <= s:
            seen_short.add(short[d - 1])
        seen_long.add(long[d - 1])
        x.append(len(seen_short & seen_long))
    x_s = x[s - 1]
    x_l = x[ll - 1]
    sum1 = sum((x[d - 1] / d) * p**d for d in range(1, ll + 1))
    sum2 = sum((x_s * (d - s)) / (s * d) * p**d for d in range(s + 1, ll + 1))
    tail = ((x_l - x_s) / ll + x_s / s) * p**ll
    value = (1.0 - p) / p * (sum1 + sum2) + tail
    value = round(value, _RBO_ROUND)
    return min(1.0, max(0.0, value))


def compare_rankings(a: Sequence[str], b: Sequence[str], *, p: float = 0.9) -> RankAgreement:
    """Bundle τ, ρ and RBO for the pair ``(a, b)`` into a :class:`RankAgreement`.

    ``n`` is the number of items common to both rankings — the support over which
    τ and ρ are defined. RBO uses the full lists and its own persistence ``p``.
    """
    return RankAgreement(
        kendall_tau=kendall_tau(a, b),
        spearman_rho=spearman_rho(a, b),
        rbo=rbo(a, b, p=p),
        n=len(_common(a, b)),
    )

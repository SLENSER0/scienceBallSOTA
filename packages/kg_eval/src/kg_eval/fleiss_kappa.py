"""Multi-annotator agreement via Fleiss' kappa для золотого набора (§18.6).

Cohen's kappa (see :mod:`kg_eval.annotator_agreement`) only handles *two* raters.
When each golden item is labelled by a fixed panel of ``n`` raters drawn from a
possibly larger pool — разметка золотых данных несколькими разметчиками (§18.6) —
agreement is measured with Fleiss' kappa instead.

Input is one ``category -> count`` mapping per item: ``n_ij`` is how many raters
assigned item ``i`` to category ``j``. Every item must have the *same* rater total
``n`` (ragged totals are a caller bug); at least two items are required.

Definitions (N items, n raters/item, categories j):

* per-item agreement ``P_i = (Σ_j n_ij² − n) / (n (n − 1))`` — fraction of rater
  *pairs* on item ``i`` that agree;
* mean observed agreement ``P̄ = (1/N) Σ_i P_i``;
* category marginal ``p_j = (1/(N n)) Σ_i n_ij`` and chance agreement
  ``P_e = Σ_j p_j²``;
* ``kappa = (P̄ − P_e) / (1 − P_e)``.

When ``P_e == 1.0`` (a single category used by everyone) kappa collapses to ``1.0``
rather than a ``0/0`` division. Kappa is clamped to ``[-1.0, 1.0]``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class FleissReport:
    """Fleiss' kappa summary over a multi-annotator golden set (§18.6).

    ``categories`` is the sorted tuple of every category seen. ``p_bar`` is mean
    observed agreement ``P̄``, ``p_e`` chance agreement ``P_e``, ``kappa`` the
    chance-corrected agreement.
    """

    n_items: int
    n_raters: int
    categories: tuple[str, ...]
    p_bar: float
    p_e: float
    kappa: float

    def as_dict(self) -> dict[str, object]:
        return {
            "n_items": self.n_items,
            "n_raters": self.n_raters,
            "categories": list(self.categories),
            "p_bar": round(self.p_bar, 4),
            "p_e": round(self.p_e, 4),
            "kappa": round(self.kappa, 4),
        }


def _rater_total(counts: Mapping[str, int]) -> int:
    """Sum of non-negative category counts for one item; negatives → ``ValueError``."""
    total = 0
    for cat, c in counts.items():
        if c < 0:
            raise ValueError(f"negative rater count for category {cat!r}: {c}")
        total += c
    return total


def fleiss_kappa(counts: Sequence[Mapping[str, int]]) -> FleissReport:
    """Compute :class:`FleissReport` from one ``category -> count`` map per item.

    Each mapping gives how many raters put that item in each category. All items
    must share the same rater total ``n`` and there must be at least two items;
    otherwise ``ValueError`` is raised.
    """
    n_items = len(counts)
    if n_items < 2:
        raise ValueError(f"need >=2 items for Fleiss' kappa, got {n_items}")

    totals = [_rater_total(item) for item in counts]
    n_raters = totals[0]
    if n_raters < 2:
        raise ValueError(f"need >=2 raters per item, got {n_raters}")
    if any(t != n_raters for t in totals):
        raise ValueError(f"ragged rater totals: {totals}")

    categories = tuple(sorted({cat for item in counts for cat in item}))

    # Mean observed agreement P̄ over per-item pair agreement.
    p_sum = 0.0
    for item in counts:
        sq = sum(item.get(cat, 0) ** 2 for cat in categories)
        p_sum += (sq - n_raters) / (n_raters * (n_raters - 1))
    p_bar = p_sum / n_items

    # Chance agreement P_e from category marginals.
    denom = n_items * n_raters
    p_e = 0.0
    for cat in categories:
        p_j = sum(item.get(cat, 0) for item in counts) / denom
        p_e += p_j * p_j

    kappa = 1.0 if p_e >= 1.0 else (p_bar - p_e) / (1.0 - p_e)
    kappa = max(-1.0, min(1.0, kappa))

    return FleissReport(
        n_items=n_items,
        n_raters=n_raters,
        categories=categories,
        p_bar=p_bar,
        p_e=p_e,
        kappa=kappa,
    )

"""Answer-quality discrimination metrics — ROC/PR AUC (§18.8).

Pure-stdlib scoring of how well a continuous *score* separates positive from
negative examples, given ``(score, label)`` pairs where ``label`` is the boolean
ground truth. Two threshold-free summaries of ranking quality:

* **ROC AUC** (area under the ROC curve) — the probability that a randomly chosen
  positive outranks a randomly chosen negative. Computed via the Mann–Whitney rank
  identity ``(Σ rank(pos) − n_pos·(n_pos+1)/2) / (n_pos·n_neg)`` with **mid-rank**
  handling of tied scores (площадь под ROC-кривой).
* **PR AUC** (average precision) — the step-wise area under the precision–recall
  curve, taken as the mean precision measured at each positive as the ranked list
  (score desc) is walked from the top (средняя точность).

Both metrics are deterministic and library-free. A perfect ranking (every positive
scored above every negative) drives both to ``1.0``. Degenerate inputs with no
positives *or* no negatives carry no discriminative signal, so ``roc_auc`` returns
``0.5`` by convention; ``pr_auc`` returns ``0.0`` when there are no positives to
retrieve and ``1.0`` when every example is positive.

Empty input is a caller bug and raises ``ValueError`` rather than returning a
vacuous report.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class AucReport:
    """Discrimination summary for a set of scored predictions (§18.8).

    ``n`` is the number of scored pairs, ``n_pos``/``n_neg`` the positive/negative
    label counts, and ``roc_auc``/``pr_auc`` the two AUC metrics. ``as_dict``
    rounds the float metrics to 4 decimals for stable serialisation.
    """

    n: int
    n_pos: int
    n_neg: int
    roc_auc: float
    pr_auc: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n": self.n,
            "n_pos": self.n_pos,
            "n_neg": self.n_neg,
            "roc_auc": round(self.roc_auc, 4),
            "pr_auc": round(self.pr_auc, 4),
        }


def _counts(pairs: Sequence[tuple[float, bool]]) -> tuple[int, int]:
    """Return ``(n_pos, n_neg)`` for ``pairs`` (labels are booleans)."""
    n_pos = sum(1 for _, label in pairs if label)
    return n_pos, len(pairs) - n_pos


def _mid_ranks(scores: Sequence[float]) -> list[float]:
    """Assign 1-based ascending ranks to ``scores`` with mid-ranks for ties."""
    n = len(scores)
    order = sorted(range(n), key=lambda i: scores[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and scores[order[j]] == scores[order[i]]:
            j += 1
        # 1-based ranks i+1 .. j share their average.
        avg_rank = ((i + 1) + j) / 2
        for k in range(i, j):
            ranks[order[k]] = avg_rank
        i = j
    return ranks


def roc_auc(pairs: Sequence[tuple[float, bool]]) -> float:
    """AUROC via the Mann–Whitney rank identity with mid-rank ties (§18.8).

    Returns ``0.5`` for degenerate inputs (all-positive or all-negative), which
    carry no discriminative signal. Raises ``ValueError`` on empty input.
    """
    if not pairs:
        raise ValueError("roc_auc requires at least one (score, label) pair")
    n_pos, n_neg = _counts(pairs)
    if n_pos == 0 or n_neg == 0:
        return 0.5
    ranks = _mid_ranks([score for score, _ in pairs])
    rank_sum_pos = sum(rank for rank, (_, label) in zip(ranks, pairs, strict=True) if label)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def pr_auc(pairs: Sequence[tuple[float, bool]]) -> float:
    """Average precision — step-wise PR-curve area, score-desc order (§18.8).

    Walks the list ordered by score descending, recording precision each time a
    positive is encountered; the mean of those precisions is the average precision.
    Returns ``0.0`` when there are no positives. Raises ``ValueError`` on empty
    input.
    """
    if not pairs:
        raise ValueError("pr_auc requires at least one (score, label) pair")
    n_pos, _ = _counts(pairs)
    if n_pos == 0:
        return 0.0
    ordered = sorted(pairs, key=lambda p: p[0], reverse=True)
    tp = 0
    fp = 0
    precision_sum = 0.0
    for _, label in ordered:
        if label:
            tp += 1
            precision_sum += tp / (tp + fp)
        else:
            fp += 1
    return precision_sum / n_pos


def analyze(pairs: Sequence[tuple[float, bool]]) -> AucReport:
    """Bundle ROC AUC + PR AUC into an :class:`AucReport` (§18.8).

    Raises ``ValueError`` on empty input.
    """
    if not pairs:
        raise ValueError("analyze requires at least one (score, label) pair")
    n_pos, n_neg = _counts(pairs)
    return AucReport(
        n=len(pairs),
        n_pos=n_pos,
        n_neg=n_neg,
        roc_auc=roc_auc(pairs),
        pr_auc=pr_auc(pairs),
    )

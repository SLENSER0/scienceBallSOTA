"""Pairwise entity-resolution cluster precision/recall/F1 (§18.7).

Scores the clustering produced by ``entity_resolver`` / Splink against a gold
clustering by comparing the *sets of co-membership pairs* they induce. Two ids in
the same predicted cluster form a predicted pair; two ids in the same gold cluster
form a gold pair. Precision then means «no false merges» (все предсказанные пары
действительно совпадают), а recall means «all expected merges found» (все золотые
пары найдены). §18.7.

This is deliberately distinct from ``confusion_matrix.py`` (binary per-item labels)
and ``crosswalk_golden.py`` (crosswalk id mapping): here the unit of evaluation is
an unordered *pair* of entity ids, so a single over-merged cluster generates
multiple false-positive pairs, capturing the combinatorial cost of a bad merge.

Zero-denominator conventions (§18.7): when the prediction induces no pairs there
are no merges to be wrong about, so precision is ``1.0``; symmetrically, when the
gold clustering induces no pairs there is nothing to recall, so recall is ``1.0``.
F1 collapses to ``0.0`` only when precision + recall == 0.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations


@dataclass(frozen=True)
class ERScores:
    """Pairwise ER scores over co-membership pairs (§18.7).

    ``tp``/``fp``/``fn`` are exact integer pair counts; ``pair_precision``,
    ``pair_recall`` и ``pair_f1`` are floats in ``[0.0, 1.0]``. There is no
    ``tn`` — non-pairs (ids never co-clustered anywhere) are not enumerated.
    """

    pair_precision: float
    pair_recall: float
    pair_f1: float
    tp: int
    fp: int
    fn: int

    def as_dict(self) -> dict[str, float | int]:
        """Serialise: integer counts exact, float ratios rounded to 4 dp."""
        return {
            "pair_precision": round(self.pair_precision, 4),
            "pair_recall": round(self.pair_recall, 4),
            "pair_f1": round(self.pair_f1, 4),
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
        }


def _same_cluster_pairs(clusters: Sequence[Sequence[str]]) -> set[frozenset]:
    """All unordered intra-cluster id pairs induced by ``clusters``.

    Each cluster contributes ``C(n, 2)`` pairs; singleton clusters contribute
    none. Pairs are ``frozenset`` so ``{a, b} == {b, a}`` and duplicates collapse.
    """
    pairs: set[frozenset] = set()
    for cluster in clusters:
        for a, b in combinations(cluster, 2):
            pairs.add(frozenset((a, b)))
    return pairs


def evaluate_er(
    predicted_clusters: Sequence[Sequence[str]],
    gold_clusters: Sequence[Sequence[str]],
) -> ERScores:
    """Pairwise precision/recall/F1 of predicted vs gold clustering (§18.7).

    Computes ``tp = |pred ∩ gold|``, ``fp = |pred − gold|`` and
    ``fn = |gold − pred|`` over co-membership pairs, then::

        precision = tp / (tp + fp)   # 1.0 when no predicted pairs
        recall    = tp / (tp + fn)   # 1.0 when no gold pairs
        f1        = 2·p·r / (p + r)  # 0.0 when p + r == 0
    """
    pred_pairs = _same_cluster_pairs(predicted_clusters)
    gold_pairs = _same_cluster_pairs(gold_clusters)

    tp = len(pred_pairs & gold_pairs)
    fp = len(pred_pairs - gold_pairs)
    fn = len(gold_pairs - pred_pairs)

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return ERScores(
        pair_precision=precision,
        pair_recall=recall,
        pair_f1=f1,
        tp=tp,
        fp=fp,
        fn=fn,
    )

"""ER quality metrics — pairwise / purity / B³ (§8.12 eval, §8.13 observability).

Оценка качества сопоставления сущностей (entity resolution) относительно
размеченного golden-набора (§8.12). All functions take clusterings as
``list[list[id]]`` / ``list[set[id]]`` — a partition of mention ids into
resolved entities — and are pure Python (no Splink / pandas), so they run in the
CI regression-gate (§8.12) and feed the ``/admin/metrics`` ER counters (§8.13).

Metrics implemented:

* :func:`pairwise_precision_recall_f1` — precision/recall/F1 over same-cluster
  pairs (the "link-based" view used for the §8.12 F1 acceptance thresholds).
* :func:`cluster_purity` / :func:`inverse_purity` — how "pure" predicted
  clusters are w.r.t. gold and vice versa.
* :func:`b_cubed_precision_recall_f1` — item-averaged B³ precision/recall/F1
  (Bagga & Baldwin), robust to both over-merging and over-splitting.
* :func:`metrics_from_resolve_result` — extract predicted clusters from a
  :class:`~kg_er.pipeline.ResolveResult` and compute all of the above.

Conventions
-----------
Predicted and gold clusterings need not enumerate the same ids: the union of ids
is taken as the universe and any id missing from a side is treated as its own
singleton (this matches the Splink path, which lists only merged records). An
empty predicted pair-set counts as precision ``1.0`` (no false merges), an empty
gold pair-set as recall ``1.0`` (nothing to recover).
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid importing Splink-backed pipeline at metrics import time
    from kg_er.pipeline import ResolveResult

Item = Hashable
Clustering = Iterable[Iterable[Item]]


# --------------------------------------------------------------------------- #
# Result containers (house style: dataclass + as_dict, §8.7 ClusterResult)     #
# --------------------------------------------------------------------------- #
@dataclass
class PRF:
    """Precision / recall / F1 triple for one metric family (§8.12)."""

    precision: float
    recall: float
    f1: float

    def as_dict(self) -> dict[str, float]:
        return {
            "precision": round(self.precision, 6),
            "recall": round(self.recall, 6),
            "f1": round(self.f1, 6),
        }


@dataclass
class ERMetrics:
    """Full ER quality report for one entity type against golden (§8.12/§8.13)."""

    pairwise: PRF
    b_cubed: PRF
    purity: float
    inverse_purity: float
    n_items: int
    n_predicted_clusters: int
    n_gold_clusters: int

    def as_dict(self) -> dict[str, object]:
        return {
            "pairwise": self.pairwise.as_dict(),
            "b_cubed": self.b_cubed.as_dict(),
            "purity": round(self.purity, 6),
            "inverse_purity": round(self.inverse_purity, 6),
            "n_items": self.n_items,
            "n_predicted_clusters": self.n_predicted_clusters,
            "n_gold_clusters": self.n_gold_clusters,
        }


# --------------------------------------------------------------------------- #
# Internal helpers                                                             #
# --------------------------------------------------------------------------- #
def _as_sets(clusters: Clustering) -> list[frozenset[Item]]:
    """Normalise any list-of-iterables clustering to a list of non-empty sets."""
    out: list[frozenset[Item]] = []
    for c in clusters:
        s = frozenset(c)
        if s:
            out.append(s)
    return out


def _universe(*clusterings: list[frozenset[Item]]) -> set[Item]:
    u: set[Item] = set()
    for cl in clusterings:
        for c in cl:
            u |= c
    return u


def _augment(clusters: list[frozenset[Item]], universe: set[Item]) -> list[frozenset[Item]]:
    """Add an implicit singleton for every universe id not already covered."""
    covered: set[Item] = set()
    for c in clusters:
        covered |= c
    extra = [frozenset({x}) for x in universe - covered]
    return clusters + extra


def _item_to_cluster(clusters: list[frozenset[Item]]) -> dict[Item, frozenset[Item]]:
    mapping: dict[Item, frozenset[Item]] = {}
    for c in clusters:
        for x in c:
            mapping[x] = c
    return mapping


def _same_cluster_pairs(clusters: list[frozenset[Item]]) -> set[frozenset[Item]]:
    """All unordered same-cluster (co-reference) pairs across the clustering."""
    pairs: set[frozenset[Item]] = set()
    for c in clusters:
        for a, b in combinations(c, 2):
            pairs.add(frozenset((a, b)))
    return pairs


def _f1(precision: float, recall: float) -> float:
    denom = precision + recall
    return 0.0 if denom == 0 else 2 * precision * recall / denom


# --------------------------------------------------------------------------- #
# Public metrics                                                              #
# --------------------------------------------------------------------------- #
def pairwise_precision_recall_f1(predicted_clusters: Clustering, gold_clusters: Clustering) -> PRF:
    """Pairwise precision/recall/F1 over same-cluster pairs (§8.12).

    A "positive" is a pair of mentions placed in the same entity. Precision =
    correct predicted pairs / predicted pairs; recall = correct predicted pairs
    / gold pairs. This is the F1 gated in CI (§8.12: Material/Equipment ≥ 0.85).
    """
    pred = _same_cluster_pairs(_as_sets(predicted_clusters))
    gold = _same_cluster_pairs(_as_sets(gold_clusters))
    true_positive = len(pred & gold)
    precision = true_positive / len(pred) if pred else 1.0
    recall = true_positive / len(gold) if gold else 1.0
    return PRF(precision, recall, _f1(precision, recall))


def cluster_purity(predicted_clusters: Clustering, gold_clusters: Clustering) -> float:
    """Purity: mean over items of the dominant gold label in their predicted cluster.

    ``purity = (1/N) · Σ_k max_j |ω_k ∩ c_j|`` where ω are predicted clusters and
    c gold clusters. High when predicted clusters are not "contaminated" — but is
    trivially 1.0 for all-singletons, hence always paired with inverse purity.
    """
    pred = _as_sets(predicted_clusters)
    gold = _as_sets(gold_clusters)
    universe = _universe(pred, gold)
    n = len(universe)
    if n == 0:
        return 1.0
    pred = _augment(pred, universe)
    gold = _augment(gold, universe)
    total = sum(max(len(c & g) for g in gold) for c in pred)
    return total / n


def inverse_purity(predicted_clusters: Clustering, gold_clusters: Clustering) -> float:
    """Inverse purity: purity with the roles of predicted and gold swapped.

    ``(1/N) · Σ_j max_k |ω_k ∩ c_j|`` — penalises over-splitting (gold entities
    scattered across many predicted clusters); trivially 1.0 for all-merged.
    """
    return cluster_purity(gold_clusters, predicted_clusters)


def b_cubed_precision_recall_f1(predicted_clusters: Clustering, gold_clusters: Clustering) -> PRF:
    """B³ (Bagga & Baldwin) item-averaged precision/recall/F1 (§8.12).

    For each item i with predicted cluster P(i) and gold cluster G(i):
    ``precision_i = |P(i) ∩ G(i)| / |P(i)|`` and
    ``recall_i    = |P(i) ∩ G(i)| / |G(i)|``. Overall values average over all
    items. Unlike pairwise F1, B³ rewards partial correctness of a cluster.
    """
    pred = _as_sets(predicted_clusters)
    gold = _as_sets(gold_clusters)
    universe = _universe(pred, gold)
    n = len(universe)
    if n == 0:
        return PRF(1.0, 1.0, 1.0)
    p_map = _item_to_cluster(_augment(pred, universe))
    g_map = _item_to_cluster(_augment(gold, universe))
    prec_sum = 0.0
    rec_sum = 0.0
    for x in universe:
        p_cluster = p_map[x]
        g_cluster = g_map[x]
        inter = len(p_cluster & g_cluster)
        prec_sum += inter / len(p_cluster)
        rec_sum += inter / len(g_cluster)
    precision = prec_sum / n
    recall = rec_sum / n
    return PRF(precision, recall, _f1(precision, recall))


def all_metrics(predicted_clusters: Clustering, gold_clusters: Clustering) -> ERMetrics:
    """Compute every §8.12 metric for one predicted/gold clustering pair."""
    pred = _as_sets(predicted_clusters)
    gold = _as_sets(gold_clusters)
    universe = _universe(pred, gold)
    return ERMetrics(
        pairwise=pairwise_precision_recall_f1(pred, gold),
        b_cubed=b_cubed_precision_recall_f1(pred, gold),
        purity=cluster_purity(pred, gold),
        inverse_purity=inverse_purity(pred, gold),
        n_items=len(universe),
        n_predicted_clusters=len(pred),
        n_gold_clusters=len(gold),
    )


def metrics_from_resolve_result(result: ResolveResult, gold_clusters: Clustering) -> ERMetrics:
    """Score a :class:`~kg_er.pipeline.ResolveResult` against golden (§8.12/§8.13).

    Extracts predicted clusters from ``result.clusters`` (each a
    :class:`~kg_er.models.base.ClusterResult` whose ``members`` is the resolved
    id tuple) and delegates to :func:`all_metrics`. Missing singletons are added
    from the golden universe, so a Splink result listing only merges still scores
    correctly.
    """
    predicted = [list(cluster.members) for cluster in result.clusters]
    return all_metrics(predicted, gold_clusters)

"""Pure-python pairwise ER clustering — Splink-free ``cluster_pairwise`` fallback (§8.4).

Транзитивная группировка пар с вероятностью совпадения (match probability) без
Splink: замена ``cluster_pairwise_predictions_at_threshold`` для случая, когда
Splink недоступен, а ``kg_retrievers.connected_components`` неприменим (он читает
граф Kuzu, а не список оценённых ER-пар).

Given a list of scored pairs ``(left_id, right_id, prob)`` and a ``threshold``,
:func:`cluster_pairs` keeps only edges with ``prob >= threshold``, runs union-find
over them, and returns one :class:`ERCluster` per connected component. Ids that
never appear in a kept edge (including any listed in ``all_ids``) form singleton
clusters. Output is fully deterministic: ``member_ids`` are sorted within each
cluster and clusters are ordered by ``member_ids``, so ``cluster_id`` is stable.

Per-cluster ``min_prob`` / ``mean_prob`` aggregate the intra-cluster *kept* edges
(the pairs at or above threshold whose endpoints both fall in that cluster);
singletons — and any cluster with no kept edges — report ``None`` for both.
"""

from __future__ import annotations

from dataclasses import dataclass

# Rounding precision for aggregated probabilities (house style: stable dict output).
_PROB_NDIGITS = 6


@dataclass(frozen=True)
class ERCluster:
    """One resolved entity cluster from pairwise ER grouping (§8.4).

    Attributes
    ----------
    cluster_id:
        Deterministic 0-based index (clusters ordered by ``member_ids``).
    member_ids:
        Sorted tuple of member mention ids (always sorted — детерминированно).
    size:
        ``len(member_ids)``.
    min_prob / mean_prob:
        Min / mean of the intra-cluster kept edge probabilities, or ``None``
        for singletons / clusters without kept edges.
    """

    cluster_id: int
    member_ids: tuple[str, ...]
    size: int
    min_prob: float | None
    mean_prob: float | None

    def as_dict(self) -> dict[str, object]:
        """Serialise for JSON / API (``member_ids`` as a list, §8.4)."""
        return {
            "cluster_id": self.cluster_id,
            "member_ids": list(self.member_ids),
            "size": self.size,
            "min_prob": self.min_prob,
            "mean_prob": self.mean_prob,
        }


class _UnionFind:
    """Minimal union-find (disjoint set) over hashable ids."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        self._parent.setdefault(item, item)

    def find(self, item: str) -> str:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        # Path compression — плоское дерево для последующих запросов.
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, left: str, right: str) -> None:
        root_left, root_right = self.find(left), self.find(right)
        if root_left != root_right:
            self._parent[root_right] = root_left


def cluster_pairs(
    pairs: list[tuple[str, str, float]],
    threshold: float,
    all_ids: list[str] | None = None,
) -> list[ERCluster]:
    """Transitively group scored ER pairs into clusters (§8.4).

    Parameters
    ----------
    pairs:
        Scored pairs ``(left_id, right_id, prob)``. Only pairs with
        ``prob >= threshold`` contribute edges; others are dropped (but their
        endpoints still appear, as singletons unless linked by another edge).
    threshold:
        Minimum match probability for an edge to be kept.
    all_ids:
        Optional universe of ids guaranteeing coverage — any id here that is not
        connected by a kept edge yields its own singleton cluster.

    Returns
    -------
    list[ERCluster]
        One cluster per connected component, ``cluster_id`` assigned in
        deterministic order (by sorted ``member_ids``).
    """
    unite = _UnionFind()

    # Register every id we know about so singletons are never lost.
    for left, right, _prob in pairs:
        unite.add(left)
        unite.add(right)
    for node in all_ids or ():
        unite.add(node)

    # Keep only edges at/above threshold; remember them for per-cluster stats.
    kept: list[tuple[str, str, float]] = []
    for left, right, prob in pairs:
        if prob >= threshold:
            kept.append((left, right, prob))
            unite.union(left, right)

    # Group member ids by their union-find root.
    members_by_root: dict[str, list[str]] = {}
    for node in unite._parent:
        members_by_root.setdefault(unite.find(node), []).append(node)

    # Collect kept-edge probabilities per root for min/mean aggregation.
    probs_by_root: dict[str, list[float]] = {}
    for left, _right, prob in kept:
        probs_by_root.setdefault(unite.find(left), []).append(prob)

    # Deterministic order: sort clusters by their sorted member_ids.
    ordered_roots = sorted(members_by_root, key=lambda r: sorted(members_by_root[r]))

    clusters: list[ERCluster] = []
    for cluster_id, root in enumerate(ordered_roots):
        member_ids = tuple(sorted(members_by_root[root]))
        edge_probs = probs_by_root.get(root, [])
        if edge_probs:
            min_prob: float | None = round(min(edge_probs), _PROB_NDIGITS)
            mean_prob: float | None = round(sum(edge_probs) / len(edge_probs), _PROB_NDIGITS)
        else:
            min_prob = None
            mean_prob = None
        clusters.append(
            ERCluster(
                cluster_id=cluster_id,
                member_ids=member_ids,
                size=len(member_ids),
                min_prob=min_prob,
                mean_prob=mean_prob,
            )
        )
    return clusters

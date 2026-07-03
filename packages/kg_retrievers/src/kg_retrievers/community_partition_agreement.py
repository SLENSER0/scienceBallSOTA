"""Numeric partition agreement between two community builds (§11.17).

``community_build_diff.py`` matches communities by set-Jaccard and reports the
structural story (stable / appeared / split / merged) — but it never yields a
single scalar "how similar are these two partitions?" number. This module fills
that gap with two label-invariant agreement scores over the **shared node set**
of two partitions:

- **Adjusted Rand Index (ARI)** — the Rand Index (fraction of node pairs whose
  same/different-cluster relationship agrees) corrected for chance. ``1.0`` for
  identical partitions (up to relabelling); ``~0.0`` for the expected value of a
  random labelling; may go negative for worse-than-random agreement.
- **Normalized Mutual Information (NMI)** — mutual information of the two
  labellings divided by the mean of their entropies. ``1.0`` for identical
  partitions; ``0.0`` when one side carries no information.

Both are computed purely from the contingency table of the two labellings, so
they are invariant to how the clusters are named (перестановка меток).

Числовое согласие двух разбиений одних и тех же узлов: скорректированный индекс
Рэнда (ARI) и нормированная взаимная информация (NMI), инвариантные к меткам.

The result is a frozen dataclass exposing ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from math import comb, log


def _contingency(
    a: Mapping[str, int], b: Mapping[str, int]
) -> tuple[Counter, Counter, Counter, int]:
    """Contingency table of two labellings over their shared nodes (§11.17).

    Returns ``(joint, rows, cols, n)`` where ``joint[(la, lb)]`` counts nodes
    labelled ``la`` in ``a`` and ``lb`` in ``b``, ``rows``/``cols`` are the
    marginals, and ``n`` is the number of common nodes (общие узлы).
    """
    common = a.keys() & b.keys()
    joint: Counter = Counter()
    rows: Counter = Counter()
    cols: Counter = Counter()
    for node in common:
        la, lb = a[node], b[node]
        joint[(la, lb)] += 1
        rows[la] += 1
        cols[lb] += 1
    return joint, rows, cols, len(common)


def adjusted_rand_index(a: Mapping[str, int], b: Mapping[str, int]) -> float:
    """Adjusted Rand Index of two labellings over their shared nodes (§11.17).

    ``1.0`` iff the partitions are identical up to relabelling; ``0.0`` for the
    chance expectation. Edge cases (``n <= 1``, or both partitions trivial) yield
    ``1.0`` when the two agree on triviality (оба тривиальны), else ``0.0``.
    """
    joint, rows, cols, n = _contingency(a, b)
    if n <= 1:
        return 1.0
    sum_comb = sum(comb(v, 2) for v in joint.values())
    sum_rows = sum(comb(v, 2) for v in rows.values())
    sum_cols = sum(comb(v, 2) for v in cols.values())
    total = comb(n, 2)
    expected = (sum_rows * sum_cols) / total
    maximum = (sum_rows + sum_cols) / 2.0
    denom = maximum - expected
    if denom == 0.0:
        # Both partitions put every pair in the same relationship (all in one
        # cluster, or all singletons): agreement is perfect iff they match.
        return 1.0 if sum_rows == sum_cols else 0.0
    return (sum_comb - expected) / denom


def _entropy(marginal: Counter, n: int) -> float:
    """Shannon entropy (nats) of a cluster-size marginal (§11.17)."""
    total = 0.0
    for count in marginal.values():
        p = count / n
        total -= p * log(p)
    return total


def normalized_mutual_info(a: Mapping[str, int], b: Mapping[str, int]) -> float:
    """Normalized Mutual Information of two labellings (§11.17).

    Mutual information divided by the arithmetic mean of the two entropies.
    ``1.0`` for identical partitions; ``0.0`` when either side has zero entropy
    (single cluster — нет информации), unless both are trivial and agree.
    """
    joint, rows, cols, n = _contingency(a, b)
    if n == 0:
        return 1.0
    h_a = _entropy(rows, n)
    h_b = _entropy(cols, n)
    if h_a == 0.0 and h_b == 0.0:
        # Both put every node in one cluster: identical, perfectly agreeing.
        return 1.0
    if h_a == 0.0 or h_b == 0.0:
        return 0.0
    mutual = 0.0
    for (la, lb), count in joint.items():
        p_joint = count / n
        p_a = rows[la] / n
        p_b = cols[lb] / n
        mutual += p_joint * log(p_joint / (p_a * p_b))
    return mutual / ((h_a + h_b) / 2.0)


@dataclass(frozen=True)
class PartitionAgreement:
    """Scalar agreement between two partitions of the same nodes (§11.17).

    - ``n_common_nodes`` — nodes present in both partitions (общие узлы);
    - ``ari`` — Adjusted Rand Index (label-invariant, chance-corrected);
    - ``nmi`` — Normalized Mutual Information (label-invariant, ``[0, 1]``).
    """

    n_common_nodes: int
    ari: float
    nmi: float

    def as_dict(self) -> dict:
        return {
            "n_common_nodes": self.n_common_nodes,
            "ari": self.ari,
            "nmi": self.nmi,
        }


def compare_partitions(a: Mapping[str, int], b: Mapping[str, int]) -> PartitionAgreement:
    """Compare two node→community labellings numerically (§11.17).

    Both scores are computed over the intersection of the two node sets, so a
    partition may safely omit nodes the other adds (сравнение по общим узлам).
    """
    n = len(a.keys() & b.keys())
    return PartitionAgreement(
        n_common_nodes=n,
        ari=adjusted_rand_index(a, b),
        nmi=normalized_mutual_info(a, b),
    )

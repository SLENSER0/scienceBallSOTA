"""Tests for partition agreement metrics ARI / NMI (§11.17).

Hand-checkable cases over tiny 4-node partitions: identical, label-permuted,
disagreeing, and the singletons-vs-one-cluster chance baseline.
"""

from __future__ import annotations

from kg_retrievers.community_partition_agreement import (
    PartitionAgreement,
    adjusted_rand_index,
    compare_partitions,
    normalized_mutual_info,
)

# Two clusters {0,1} and {2,3}.
A = {"0": 0, "1": 0, "2": 1, "3": 1}
# Same two clusters, labels swapped 0<->1.
B = {"0": 1, "1": 1, "2": 0, "3": 0}
# Different cut: {0,2} and {1,3}.
C = {"0": 0, "1": 1, "2": 0, "3": 1}


def test_identical_partition_is_perfect() -> None:
    assert adjusted_rand_index(A, A) == 1.0
    assert normalized_mutual_info(A, A) == 1.0


def test_label_permutation_is_invariant() -> None:
    # B is A with cluster labels swapped: the partition is the same.
    assert adjusted_rand_index(A, B) == 1.0
    assert normalized_mutual_info(A, B) == 1.0


def test_disagreeing_partition_is_imperfect() -> None:
    assert adjusted_rand_index(A, C) < 1.0
    assert normalized_mutual_info(A, C) < 1.0


def test_singletons_vs_one_cluster_is_chance() -> None:
    singletons = {"0": 0, "1": 1, "2": 2, "3": 3}
    one_cluster = {"0": 0, "1": 0, "2": 0, "3": 0}
    ari = adjusted_rand_index(singletons, one_cluster)
    assert abs(ari) < 1e-9
    # No shared information: NMI is 0 (one_cluster carries zero entropy).
    assert normalized_mutual_info(singletons, one_cluster) == 0.0


def test_compare_partitions_counts_common_nodes() -> None:
    result = compare_partitions(A, B)
    assert isinstance(result, PartitionAgreement)
    assert result.n_common_nodes == 4
    assert result.ari == 1.0
    assert result.nmi == 1.0


def test_as_dict_round_trip_for_identical() -> None:
    d = compare_partitions(A, A).as_dict()
    assert d["n_common_nodes"] == 4
    assert d["ari"] == 1.0
    assert d["nmi"] == 1.0


def test_disjoint_node_sets_intersect_to_common() -> None:
    left = {"0": 0, "1": 0, "2": 1}
    right = {"1": 5, "2": 5, "9": 7}  # shares only nodes "1","2"
    result = compare_partitions(left, right)
    assert result.n_common_nodes == 2


def test_ari_can_go_negative_for_worse_than_random() -> None:
    # Two clusters vs the exact "checkerboard" opposite pairing.
    p = {"0": 0, "1": 0, "2": 1, "3": 1}
    q = {"0": 0, "1": 1, "2": 0, "3": 1}
    assert adjusted_rand_index(p, q) <= 0.0

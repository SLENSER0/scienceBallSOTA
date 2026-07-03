"""Tests for edge-based partition-quality metrics (§11.13).

Hand-checkable fixture: two triangles {1,2,3} and {4,5,6} joined by a single
bridge edge 3-4, giving m=7 undirected simple edges.
"""

from __future__ import annotations

from kg_retrievers.community_partition_quality import (
    PartitionQuality,
    community_conductance,
    coverage,
    evaluate_partition,
    modularity,
)

# Two triangles joined by bridge 3-4 (m = 7 edges).
_EDGES: list[tuple[str, str]] = [
    ("1", "2"),
    ("1", "3"),
    ("2", "3"),
    ("4", "5"),
    ("4", "6"),
    ("5", "6"),
    ("3", "4"),
]
_A = 0
_B = 1
_MEMBERSHIP = {"1": _A, "2": _A, "3": _A, "4": _B, "5": _B, "6": _B}


def test_modularity_two_triangles() -> None:
    # Q = 2*[3/7 - (7/14)^2] = 0.357142857...
    assert abs(modularity(_EDGES, _MEMBERSHIP) - 0.357142857) < 1e-6


def test_coverage_two_triangles() -> None:
    # 6 intra-community edges out of 7.
    assert coverage(_EDGES, _MEMBERSHIP) == 6 / 7


def test_community_conductance_bridge() -> None:
    cond = community_conductance(_EDGES, _MEMBERSHIP)
    # cut=1 (the bridge), vol_A = vol_B = 7 -> 1/min(7,7) = 1/7.
    assert cond[_A] == 1 / 7
    assert cond[_B] == 1 / 7


def test_evaluate_partition_bundle() -> None:
    pq = evaluate_partition(_EDGES, _MEMBERSHIP)
    assert isinstance(pq, PartitionQuality)
    assert pq.n_communities == 2
    assert abs(pq.modularity - 0.357142857) < 1e-6
    assert pq.coverage == 6 / 7
    assert pq.avg_conductance == 1 / 7


def test_empty_graph() -> None:
    assert modularity([], {}) == 0.0
    assert coverage([], {}) == 0.0
    assert community_conductance([], {}) == {}
    pq = evaluate_partition([], {})
    assert pq.n_communities == 0
    assert pq.avg_conductance == 0.0


def test_single_community_partition() -> None:
    one = dict.fromkeys(_MEMBERSHIP, _A)
    # All edges intra-community -> coverage 1.0.
    assert coverage(_EDGES, one) == 1.0
    cond = community_conductance(_EDGES, one)
    # min(vol_c, vol_notc) = min(14, 0) = 0 -> conductance defined as 0.0.
    assert all(v == 0.0 for v in cond.values())
    assert cond[_A] == 0.0


def test_self_loops_and_parallel_edges_collapsed() -> None:
    noisy = [*_EDGES, ("1", "1"), ("2", "1"), ("3", "1")]
    # Self-loop (1,1) dropped; (2,1)/(3,1) are duplicates of existing edges.
    assert coverage(noisy, _MEMBERSHIP) == 6 / 7
    assert abs(modularity(noisy, _MEMBERSHIP) - 0.357142857) < 1e-6


def test_as_dict_round_trips_modularity() -> None:
    pq = evaluate_partition(_EDGES, _MEMBERSHIP)
    d = pq.as_dict()
    assert d["modularity"] == pq.modularity
    assert d["n_communities"] == 2
    assert d["per_community_conductance"] == pq.per_community_conductance

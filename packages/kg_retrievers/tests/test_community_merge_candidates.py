"""Tests for §11.6 over-partition merge recommendation via edge coupling.

Pure in-memory tests with hand-checked coupling values; no store required.
"""

from __future__ import annotations

from kg_retrievers.community_merge_candidates import (
    MergeCandidate,
    merge_candidates,
)

# Two communities {1,2}=0 and {3,4}=1 with one internal edge each and three
# cross edges: coupling = 3 / (3 + 1 + 1) = 0.6.
_MEMBERSHIP = {"1": 0, "2": 0, "3": 1, "4": 1}
_EDGES = [("1", "2"), ("3", "4"), ("1", "3"), ("2", "4"), ("1", "4")]


def test_cross_edge_count() -> None:
    assert merge_candidates(_EDGES, _MEMBERSHIP)[0].cross_edges == 3


def test_internal_edge_counts() -> None:
    top = merge_candidates(_EDGES, _MEMBERSHIP)[0]
    assert top.internal_a == 1 and top.internal_b == 1


def test_coupling_exact_value() -> None:
    assert abs(merge_candidates(_EDGES, _MEMBERSHIP)[0].coupling - 0.6) < 1e-9


def test_min_coupling_filters_out() -> None:
    assert merge_candidates(_EDGES, _MEMBERSHIP, min_coupling=0.9) == []


def test_single_community_yields_nothing() -> None:
    assert merge_candidates([("1", "2")], {"1": 0, "2": 0}) == []


def test_ordered_community_ids() -> None:
    top = merge_candidates(_EDGES, _MEMBERSHIP)[0]
    assert top.community_a == 0 and top.community_b == 1


def test_as_dict_round_trips_cross_edges() -> None:
    assert merge_candidates(_EDGES, _MEMBERSHIP)[0].as_dict()["cross_edges"] == 3


def test_returns_merge_candidate_instances() -> None:
    result = merge_candidates(_EDGES, _MEMBERSHIP)
    assert len(result) == 1
    assert isinstance(result[0], MergeCandidate)


def test_min_cross_filters_out() -> None:
    # Only one cross edge between communities 0 and 1; internal edges keep
    # coupling low too, but min_cross=2 excludes it outright.
    edges = [("1", "2"), ("3", "4"), ("1", "3")]
    assert merge_candidates(edges, _MEMBERSHIP, min_cross=2) == []


def test_sorted_by_coupling_desc() -> None:
    # Communities 0 and 1 fully cross-coupled (coupling 1.0); 2 loosely coupled
    # to 0 with an internal edge lowering its score below the 0-1 pair.
    membership = {"a": 0, "b": 1, "c": 2, "d": 2}
    edges = [
        ("a", "b"),  # cross 0-1
        ("c", "d"),  # internal 2
        ("a", "c"),  # cross 0-2
        ("a", "c"),  # cross 0-2 (duplicate edge, counted again)
    ]
    result = merge_candidates(edges, membership)
    couplings = [c.coupling for c in result]
    assert couplings == sorted(couplings, reverse=True)
    assert result[0].community_a == 0 and result[0].community_b == 1

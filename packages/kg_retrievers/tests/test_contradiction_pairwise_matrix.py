"""Tests for the pairwise divergence matrix (§15.4).

Hand-checkable: divergence is ``|a-b| / max(|a|,|b|)``; for 100 vs 130 that is
``30 / 130 == 0.230769… → 0.2308`` (4 dp).
"""

from __future__ import annotations

from kg_retrievers.contradiction_pairwise_matrix import (
    PairwiseDivergence,
    pairwise_divergence,
)


def test_identical_values_no_conflict() -> None:
    result = pairwise_divergence(
        [{"id": "m0", "value_normalized": 100.0}, {"id": "m1", "value_normalized": 100.0}]
    )
    assert result.matrix == ((0.0, 0.0), (0.0, 0.0))
    assert result.conflict_pairs == ()
    assert result.max_divergence == 0.0


def test_divergent_values_flagged() -> None:
    result = pairwise_divergence(
        [{"id": "m0", "value_normalized": 100.0}, {"id": "m1", "value_normalized": 130.0}]
    )
    assert result.matrix[0][1] == 0.2308
    assert result.matrix[1][0] == 0.2308
    assert result.max_divergence == 0.2308
    assert ("m0", "m1") in result.conflict_pairs


def test_matrix_symmetric_and_zero_diagonal() -> None:
    result = pairwise_divergence(
        [
            {"id": "m0", "value_normalized": 100.0},
            {"id": "m1", "value_normalized": 130.0},
            {"id": "m2", "value_normalized": 50.0},
        ]
    )
    n = len(result.ids)
    for i in range(n):
        assert result.matrix[i][i] == 0.0
        for j in range(n):
            assert result.matrix[i][j] == result.matrix[j][i]


def test_overlapping_ci_suppresses_conflict() -> None:
    # 130 vs 100 diverges by 0.2308 > rel_tol, but the CIs [90,140] and [95,110]
    # overlap → no conflict pair.
    result = pairwise_divergence(
        [
            {"id": "m0", "value_normalized": 130.0, "ci_low": 90.0, "ci_high": 140.0},
            {"id": "m1", "value_normalized": 100.0, "ci_low": 95.0, "ci_high": 110.0},
        ]
    )
    assert result.matrix[0][1] == 0.2308
    assert result.max_divergence == 0.2308
    assert result.conflict_pairs == ()


def test_disjoint_ci_still_conflicts() -> None:
    # Same divergence but disjoint CIs → the conflict stands.
    result = pairwise_divergence(
        [
            {"id": "m0", "value_normalized": 130.0, "ci_low": 120.0, "ci_high": 140.0},
            {"id": "m1", "value_normalized": 100.0, "ci_low": 95.0, "ci_high": 110.0},
        ]
    )
    assert ("m0", "m1") in result.conflict_pairs


def test_single_measurement() -> None:
    result = pairwise_divergence([{"id": "only", "value_normalized": 42.0}])
    assert result.matrix == ((0.0,),)
    assert result.conflict_pairs == ()
    assert result.max_divergence == 0.0


def test_as_dict_exposes_ids_and_max_divergence() -> None:
    result = pairwise_divergence(
        [{"id": "m0", "value_normalized": 100.0}, {"id": "m1", "value_normalized": 130.0}]
    )
    d = result.as_dict()
    assert d["ids"] == ["m0", "m1"]
    assert d["max_divergence"] == 0.2308
    assert d["conflict_pairs"] == [["m0", "m1"]]
    assert isinstance(result, PairwiseDivergence)

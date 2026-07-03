"""Tests for rank-agreement metrics (§12.11).

Hand-checkable ranking-agreement assertions: identical / reversed / disjoint
extremes plus the top-weighting property of RBO.
"""

from __future__ import annotations

import pytest

from kg_retrievers.rank_correlation import (
    RankAgreement,
    compare_rankings,
    kendall_tau,
    rbo,
    spearman_rho,
)


def test_kendall_tau_identical_is_one() -> None:
    # Assertion (1): identical order -> every common pair concordant -> τ = 1.
    assert kendall_tau(["a", "b", "c"], ["a", "b", "c"]) == 1.0


def test_kendall_tau_reversed_is_minus_one() -> None:
    # Assertion (2): fully reversed order -> every pair discordant -> τ = -1.
    assert kendall_tau(["a", "b", "c"], ["c", "b", "a"]) == -1.0


def test_spearman_rho_identical_is_one() -> None:
    # Assertion (3): identical ranks -> Σd² = 0 -> ρ = 1.
    assert spearman_rho(["a", "b", "c"], ["a", "b", "c"]) == 1.0


def test_spearman_rho_reversed_is_minus_one() -> None:
    # Assertion (4): fully reversed ranks -> ρ = -1 (n=3: 1 - 6·8/24 = -1).
    assert spearman_rho(["a", "b", "c"], ["c", "b", "a"]) == -1.0


def test_rbo_identical_is_one() -> None:
    # Assertion (5): identical lists -> perfect overlap at every depth -> RBO = 1.
    assert rbo(["a", "b", "c"], ["a", "b", "c"]) == 1.0


def test_rbo_disjoint_is_zero() -> None:
    # Assertion (6): no shared items at any depth -> RBO = 0.
    assert rbo(["a", "b", "c"], ["x", "y", "z"]) == 0.0


def test_rbo_top_weighting_beats_bottom() -> None:
    # Assertion (7): sharing only the *top* item scores higher than sharing only
    # the *bottom* item, because RBO weights early ranks more.
    top_shared = rbo(["x", "a", "b"], ["x", "c", "d"])
    bottom_shared = rbo(["a", "b", "x"], ["c", "d", "x"])
    assert top_shared > bottom_shared
    # Both share exactly one item, so both lie strictly inside (0, 1).
    assert 0.0 < bottom_shared < top_shared < 1.0


def test_compare_rankings_n_equals_common_set_size() -> None:
    # Assertion (8): n is the size of the common-item set (here {b, c} -> 2).
    result = compare_rankings(["a", "b", "c"], ["b", "c", "d"])
    assert isinstance(result, RankAgreement)
    assert result.n == 2


def test_as_dict_exposes_all_four_fields() -> None:
    # Assertion (9): as_dict() surfaces every field of the frozen dataclass.
    result = compare_rankings(["a", "b", "c"], ["a", "b", "c"])
    d = result.as_dict()
    assert set(d) == {"kendall_tau", "spearman_rho", "rbo", "n"}
    assert d["kendall_tau"] == 1.0
    assert d["spearman_rho"] == 1.0
    assert d["rbo"] == 1.0
    assert d["n"] == 3


def test_rank_agreement_is_frozen() -> None:
    result = compare_rankings(["a", "b"], ["a", "b"])
    with pytest.raises((AttributeError, TypeError)):
        result.rbo = 0.5  # type: ignore[misc]


def test_rbo_rejects_out_of_range_p() -> None:
    with pytest.raises(ValueError):
        rbo(["a"], ["a"], p=1.0)
    with pytest.raises(ValueError):
        rbo(["a"], ["a"], p=0.0)


def test_partial_overlap_is_between_extremes() -> None:
    # A single swap of adjacent middle items: agreement is high but < 1.
    tau = kendall_tau(["a", "b", "c", "d"], ["a", "c", "b", "d"])
    rho = spearman_rho(["a", "b", "c", "d"], ["a", "c", "b", "d"])
    assert -1.0 < tau < 1.0
    assert -1.0 < rho < 1.0

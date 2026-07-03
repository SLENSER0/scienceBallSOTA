"""Tests for the exact paired permutation (sign-flip) test (§18.11)."""

from __future__ import annotations

import pytest

from kg_eval.permutation_test import PermutationResult, paired_permutation


def test_exact_small_hand_checked() -> None:
    """diffs all == 1 → 2 of 8 flips reach |mean| >= 1, so p == 0.25."""
    result = paired_permutation([2.0, 2.0, 2.0], [1.0, 1.0, 1.0])
    assert result.observed_diff == 1.0
    assert result.p_value == 0.25
    assert result.exact is True
    assert result.n == 3


def test_exact_n_resamples_is_two_pow_n() -> None:
    """On the exact path for n == 3, n_resamples reports 2 ** 3 == 8."""
    result = paired_permutation([2.0, 2.0, 2.0], [1.0, 1.0, 1.0])
    assert result.n_resamples == 8


def test_identical_inputs_pvalue_one() -> None:
    """All diffs zero → every flip ties the observed |mean| of 0, p == 1.0."""
    result = paired_permutation([5.0, 5.0, 5.0], [5.0, 5.0, 5.0])
    assert result.observed_diff == 0.0
    assert result.p_value == 1.0
    assert result.exact is True


def test_sampled_path_reproducible() -> None:
    """n=25 > max_exact: same seed → identical sampled p_value."""
    system = [float(i % 3) for i in range(25)]
    baseline = [float((i + 1) % 3) for i in range(25)]
    r1 = paired_permutation(system, baseline, seed=7, n_resamples=2000)
    r2 = paired_permutation(system, baseline, seed=7, n_resamples=2000)
    assert r1.exact is False
    assert r1.n == 25
    assert r1.p_value == r2.p_value


def test_different_seeds_valid_range() -> None:
    """Different seeds may differ but both p_values lie in [0, 1]."""
    system = [float(i % 4) for i in range(25)]
    baseline = [float((i * 2 + 1) % 4) for i in range(25)]
    r_a = paired_permutation(system, baseline, seed=1, n_resamples=2000)
    r_b = paired_permutation(system, baseline, seed=999, n_resamples=2000)
    assert 0.0 <= r_a.p_value <= 1.0
    assert 0.0 <= r_b.p_value <= 1.0


def test_empty_input_raises() -> None:
    """Empty input raises ValueError."""
    with pytest.raises(ValueError):
        paired_permutation([], [])


def test_length_mismatch_raises() -> None:
    """Length mismatch raises ValueError."""
    with pytest.raises(ValueError):
        paired_permutation([1.0, 2.0], [1.0])


def test_as_dict_exact_flag() -> None:
    """as_dict() exposes exact == True for n == 3 and round-trips fields."""
    result = paired_permutation([2.0, 2.0, 2.0], [1.0, 1.0, 1.0])
    d = result.as_dict()
    assert d["exact"] is True
    assert d["n"] == 3
    assert d["p_value"] == 0.25
    assert d["n_resamples"] == 8


def test_result_is_frozen() -> None:
    """PermutationResult is an immutable frozen dataclass."""
    result = paired_permutation([2.0, 2.0, 2.0], [1.0, 1.0, 1.0])
    assert isinstance(result, PermutationResult)
    with pytest.raises(AttributeError):
        result.p_value = 0.0  # type: ignore[misc]

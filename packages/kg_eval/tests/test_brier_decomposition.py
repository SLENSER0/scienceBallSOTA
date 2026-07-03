"""Tests for Murphy's Brier-score decomposition (§18.8)."""

from __future__ import annotations

import pytest

from kg_eval.brier_decomposition import BrierDecomposition, brier_decomposition


def test_two_bin_perfectly_confident() -> None:
    """[(0,F),(0,F),(1,T),(1,T)] n_bins=2: rel=0, res=0.25, unc=0.25, brier=0."""
    pairs = [(0.0, False), (0.0, False), (1.0, True), (1.0, True)]
    d = brier_decomposition(pairs, n_bins=2)
    assert d.reliability == 0.0
    assert d.resolution == 0.25
    assert d.uncertainty == 0.25
    assert d.brier == 0.0


def test_identity_matches_direct_mse_mixed_sample() -> None:
    """rel - res + unc equals direct mean (f - o)^2 when forecasts are bin-constant."""
    pairs = [
        (0.15, True),
        (0.15, False),
        (0.15, False),
        (0.15, False),
        (0.55, True),
        (0.55, True),
        (0.55, False),
        (0.85, True),
        (0.85, True),
        (0.85, True),
        (0.85, False),
    ]
    d = brier_decomposition(pairs, n_bins=10)
    direct = sum((f - (1.0 if o else 0.0)) ** 2 for f, o in pairs) / len(pairs)
    assert abs((d.reliability - d.resolution + d.uncertainty) - direct) < 1e-9
    assert abs(d.brier - direct) < 1e-9


def test_all_same_outcome_zero_uncertainty() -> None:
    """A sample with a single outcome value has zero irreducible uncertainty."""
    pairs = [(0.2, True), (0.6, True), (0.9, True)]
    d = brier_decomposition(pairs, n_bins=5)
    assert d.uncertainty == 0.0


def test_perfectly_calibrated_zero_reliability() -> None:
    """When conf_k equals o_k in every bin, reliability is exactly zero."""
    # Bin containing 0.5: two forecasts, exactly one hit -> o_k = 0.5 = conf_k.
    pairs = [(0.5, True), (0.5, False)]
    d = brier_decomposition(pairs, n_bins=10)
    assert d.reliability == 0.0


def test_records_n_and_n_bins() -> None:
    """n and n_bins are stored verbatim."""
    pairs = [(0.1, False), (0.9, True), (0.4, True)]
    d = brier_decomposition(pairs, n_bins=7)
    assert d.n == 3
    assert d.n_bins == 7


def test_empty_pairs_raise() -> None:
    """Empty input is a caller bug."""
    with pytest.raises(ValueError):
        brier_decomposition([], n_bins=2)


def test_as_dict_brier_case_one() -> None:
    """as_dict()['brier'] == 0.0 for the two-bin perfectly-confident case."""
    pairs = [(0.0, False), (0.0, False), (1.0, True), (1.0, True)]
    d = brier_decomposition(pairs, n_bins=2)
    assert isinstance(d, BrierDecomposition)
    assert d.as_dict()["brier"] == 0.0

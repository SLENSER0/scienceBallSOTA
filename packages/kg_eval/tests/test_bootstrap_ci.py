"""Tests for single-metric bootstrap CI (§18.11)."""

from __future__ import annotations

import pytest

from kg_eval.bootstrap_ci import BootstrapCI, bootstrap_ci


def test_constant_sample_collapses_to_point() -> None:
    """A constant sample has zero spread → point == lower == upper."""
    result = bootstrap_ci([0.5] * 10, seed=0)
    assert result.point == 0.5
    assert result.lower == 0.5
    assert result.upper == 0.5


def test_bounds_bracket_point_for_mixed_sample() -> None:
    """For a spread-out sample the interval brackets the plug-in point."""
    result = bootstrap_ci([0.1, 0.4, 0.5, 0.6, 0.9], seed=3)
    assert result.lower <= result.point <= result.upper


def test_reproducible_with_same_seed() -> None:
    """Two calls with the same seed give identical bounds."""
    sample = [0.2, 0.3, 0.7, 0.8, 0.55, 0.61]
    a = bootstrap_ci(sample, seed=1)
    b = bootstrap_ci(sample, seed=1)
    assert a.lower == b.lower
    assert a.upper == b.upper


def test_wider_confidence_encloses_narrower() -> None:
    """A 0.99 interval encloses the 0.90 interval on the same sample+seed."""
    sample = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    ci90 = bootstrap_ci(sample, confidence=0.90, seed=7)
    ci99 = bootstrap_ci(sample, confidence=0.99, seed=7)
    assert ci99.lower <= ci90.lower
    assert ci99.upper >= ci90.upper


def test_empty_sample_raises() -> None:
    with pytest.raises(ValueError):
        bootstrap_ci([])


def test_confidence_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        bootstrap_ci([0.1, 0.2, 0.3], confidence=1.5)


def test_as_dict_reports_default_n_resamples() -> None:
    result = bootstrap_ci([0.3, 0.6, 0.9], seed=0)
    assert isinstance(result, BootstrapCI)
    assert result.as_dict()["n_resamples"] == 2000

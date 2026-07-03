"""Tests for the Wilson score confidence interval (§25.19).

Тесты интервала Уилсона — every expected bound below is hand-checkable from the
Wilson formula; the 50/100 case is the canonical textbook value.
"""

from __future__ import annotations

from math import isclose

from kg_retrievers.recall_wilson_ci import WilsonInterval, wilson_interval


def test_canonical_50_of_100() -> None:
    """successes=50, n=100, z=1.96 -> point 0.5, bounds ~0.4038 / 0.5962."""
    ci = wilson_interval(50, 100, z=1.96)
    assert ci.point == 0.5
    assert isclose(ci.lower, 0.4038, abs_tol=1e-3)
    assert isclose(ci.upper, 0.5962, abs_tol=1e-3)


def test_empty_sample_is_maximally_uninformative() -> None:
    """n == 0 -> point 0.0, full [0, 1] span."""
    ci = wilson_interval(0, 0)
    assert ci.point == 0.0
    assert ci.lower == 0.0
    assert ci.upper == 1.0
    assert ci.width == 1.0
    assert ci.n == 0


def test_all_successes_bounds() -> None:
    """successes == n -> point 1.0, informative lower ~0.7225, upper capped at 1.0.

    Note: continuity-free Wilson saturates upper to exactly 1.0 at ``p == 1`` (it is an
    algebraic identity that ``center + half == 1`` there), so the meaningful content is
    the non-degenerate lower bound. This is Wilson's advantage over Wald, which reports
    the useless ``[1.0, 1.0]`` at ``k == n``.
    """
    ci = wilson_interval(10, 10)
    assert ci.point == 1.0
    assert isclose(ci.lower, 0.7225, abs_tol=1e-3)
    assert 0.0 < ci.lower < 1.0
    assert ci.upper <= 1.0


def test_zero_successes_lower_is_zero() -> None:
    """successes == 0 -> point 0.0 and lower pinned at 0.0."""
    ci = wilson_interval(0, 10)
    assert ci.point == 0.0
    assert ci.lower == 0.0
    assert ci.upper > 0.0


def test_bounds_bracket_point() -> None:
    """lower <= point <= upper holds across the whole range of successes."""
    for k in range(0, 21):
        ci = wilson_interval(k, 20)
        assert ci.lower <= ci.point <= ci.upper


def test_larger_n_narrows_width() -> None:
    """Same proportion (0.9) with larger n gives a tighter interval."""
    assert wilson_interval(90, 100).width < wilson_interval(9, 10).width


def test_width_equals_upper_minus_lower() -> None:
    """width is exactly upper - lower."""
    ci = wilson_interval(37, 58)
    assert ci.width == ci.upper - ci.lower


def test_as_dict_defaults_and_rounding() -> None:
    """as_dict() reports the default z and rounds floats to 4 decimals."""
    ci = wilson_interval(50, 100)
    d = ci.as_dict()
    assert d["z"] == 1.96
    assert d["point"] == 0.5
    assert d["lower"] == 0.4038
    assert d["upper"] == 0.5962
    assert d["n"] == 100
    assert isinstance(ci, WilsonInterval)

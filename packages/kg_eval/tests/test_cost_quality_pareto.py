"""Tests for cost/quality Pareto-frontier selection (§23.10/§23.31).

Hand-checkable cases: single config, strictly-worse domination, equal-cost
domination, identical duplicates, knee selection, cheaper-and-better sweep, and
the empty-input ``ValueError``.
"""

from __future__ import annotations

import pytest

from kg_eval.cost_quality_pareto import (
    ConfigPoint,
    ParetoReport,
    compute_pareto,
    compute_points,
)


def _by_name(points: tuple[ConfigPoint, ...]) -> dict[str, ConfigPoint]:
    return {p.name: p for p in points}


def test_single_config_is_lone_frontier_not_dominated() -> None:
    report = compute_pareto({"only": {"cost": 2.0, "quality": 8.0}})
    assert report.frontier == ("only",)
    assert report.dominated == ()
    assert report.knee == "only"
    point = _by_name(compute_points({"only": {"cost": 2.0, "quality": 8.0}}))["only"]
    assert point.dominated is False
    assert point.dominated_by == ()


def test_strictly_worse_config_is_dominated_by_the_better() -> None:
    # good: cheaper AND higher quality; bad: pricier AND lower quality.
    configs = {
        "good": {"cost": 1.0, "quality": 9.0},
        "bad": {"cost": 3.0, "quality": 4.0},
    }
    report = compute_pareto(configs)
    assert report.frontier == ("good",)
    assert report.dominated == ("bad",)
    points = _by_name(compute_points(configs))
    assert points["bad"].dominated is True
    assert points["bad"].dominated_by == ("good",)
    assert points["good"].dominated is False
    assert points["good"].dominated_by == ()


def test_equal_cost_lower_quality_is_dominated() -> None:
    configs = {
        "hi": {"cost": 2.0, "quality": 7.0},
        "lo": {"cost": 2.0, "quality": 5.0},
    }
    report = compute_pareto(configs)
    # Same cost => the lower-quality point is dominated by the higher-quality one.
    assert report.frontier == ("hi",)
    assert report.dominated == ("lo",)
    points = _by_name(compute_points(configs))
    assert points["lo"].dominated_by == ("hi",)


def test_identical_duplicates_neither_dominates_both_on_frontier() -> None:
    configs = {
        "a": {"cost": 2.0, "quality": 6.0},
        "b": {"cost": 2.0, "quality": 6.0},
    }
    report = compute_pareto(configs)
    # No strict inequality between equals => neither is dominated.
    assert set(report.frontier) == {"a", "b"}
    assert report.dominated == ()
    points = _by_name(compute_points(configs))
    assert points["a"].dominated is False
    assert points["b"].dominated is False
    assert points["a"].dominated_by == ()
    assert points["b"].dominated_by == ()


def test_frontier_sorted_by_cost_ascending() -> None:
    # A classic trade-off frontier: cost up, quality up — none dominates another.
    configs = {
        "mid": {"cost": 5.0, "quality": 7.0},
        "cheap": {"cost": 2.0, "quality": 4.0},
        "rich": {"cost": 9.0, "quality": 9.0},
    }
    report = compute_pareto(configs)
    assert report.frontier == ("cheap", "mid", "rich")
    assert report.dominated == ()
    costs = [configs[name]["cost"] for name in report.frontier]
    assert costs == sorted(costs)


def test_knee_picks_best_quality_over_cost_ratio() -> None:
    # ratios: cheap 4/2=2.0, mid 7/5=1.4, rich 9/9=1.0 -> knee = cheap.
    configs = {
        "cheap": {"cost": 2.0, "quality": 4.0},
        "mid": {"cost": 5.0, "quality": 7.0},
        "rich": {"cost": 9.0, "quality": 9.0},
    }
    report = compute_pareto(configs)
    assert report.knee == "cheap"


def test_knee_falls_back_to_max_quality_when_cost_non_positive() -> None:
    # zero-cost point makes quality/cost ill-defined => pick max quality on frontier.
    configs = {
        "free": {"cost": 0.0, "quality": 3.0},
        "paid": {"cost": 4.0, "quality": 8.0},
    }
    report = compute_pareto(configs)
    assert report.frontier == ("free", "paid")
    assert report.knee == "paid"


def test_cheaper_and_better_point_dominates_all_others() -> None:
    configs = {
        "king": {"cost": 1.0, "quality": 10.0},
        "x": {"cost": 4.0, "quality": 6.0},
        "y": {"cost": 7.0, "quality": 2.0},
    }
    report = compute_pareto(configs)
    assert report.frontier == ("king",)
    assert len(report.frontier) == 1
    assert report.dominated == ("x", "y")
    assert report.knee == "king"


def test_empty_configs_raises_value_error() -> None:
    with pytest.raises(ValueError):
        compute_pareto({})
    with pytest.raises(ValueError):
        compute_points({})


def test_report_as_dict_round_trip() -> None:
    report = compute_pareto({"only": {"cost": 2.0, "quality": 8.0}})
    assert report.as_dict() == {
        "frontier": ["only"],
        "dominated": [],
        "knee": "only",
    }
    assert isinstance(report, ParetoReport)


def test_point_as_dict_shape() -> None:
    points = _by_name(
        compute_points(
            {
                "good": {"cost": 1.0, "quality": 9.0},
                "bad": {"cost": 3.0, "quality": 4.0},
            }
        )
    )
    assert points["bad"].as_dict() == {
        "name": "bad",
        "cost": 3.0,
        "quality": 4.0,
        "dominated": True,
        "dominated_by": ["good"],
    }

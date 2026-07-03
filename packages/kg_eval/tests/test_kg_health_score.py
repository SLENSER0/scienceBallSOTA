"""Tests for the composite KG health score (§23.24)."""

from __future__ import annotations

import pytest

from kg_eval.kg_health_score import (
    DEFAULT_WEIGHTS,
    LOWER_IS_BETTER,
    Component,
    HealthScore,
    component_contribution,
    kg_health_score,
)


def test_all_perfect_metrics_score_100_grade_a_gate_passed() -> None:
    hs = kg_health_score({"evidence_coverage": 1.0, "orphan_rate": 0.0, "duplicate_rate": 0.0})
    assert hs.score == 100.0
    assert hs.grade == "A"
    assert hs.gate_passed is True
    assert hs.failing == ()
    assert len(hs.components) == 3


def test_all_worst_metrics_score_0_grade_f() -> None:
    hs = kg_health_score({"evidence_coverage": 0.0, "orphan_rate": 1.0, "duplicate_rate": 1.0})
    assert hs.score == 0.0
    assert hs.grade == "F"


def test_orphan_rate_is_inverted_raw_one_contributes_zero() -> None:
    # lower-is-better: raw=1.0 -> effective 0.0 -> contribution 0.0.
    assert component_contribution("orphan_rate", 1.0, 2.0) == 0.0
    # raw=0.0 -> effective 1.0 -> full weight.
    assert component_contribution("orphan_rate", 0.0, 2.0) == 2.0
    # higher-is-better passes through unchanged.
    assert component_contribution("evidence_coverage", 0.5, 3.0) == 1.5


def test_grade_boundary_75_maps_to_b() -> None:
    # coverage=0.75, sole component weight 3.0 -> score = 100*0.75 = 75.0.
    hs = kg_health_score({"evidence_coverage": 0.75})
    assert hs.score == 75.0
    assert hs.grade == "B"


def test_grade_boundaries_abcdf() -> None:
    def grade_for(cov: float) -> str:
        return kg_health_score({"evidence_coverage": cov}).grade

    # Mid-band values, kept off exact 0.60/0.40 to dodge float boundary noise.
    assert grade_for(0.95) == "A"
    assert grade_for(0.80) == "B"
    assert grade_for(0.70) == "C"
    assert grade_for(0.50) == "D"
    assert grade_for(0.20) == "F"


def test_failing_lists_names_below_threshold() -> None:
    hs = kg_health_score(
        {"evidence_coverage": 0.5, "orphan_rate": 0.9},
        thresholds={"evidence_coverage": 0.8, "orphan_rate": 0.8},
    )
    # coverage effective 0.5 < 0.8; orphan effective (1-0.9)=0.1 < 0.8.
    assert set(hs.failing) == {"evidence_coverage", "orphan_rate"}
    assert hs.gate_passed is False


def test_threshold_pass_keeps_gate_open() -> None:
    hs = kg_health_score(
        {"evidence_coverage": 0.95, "orphan_rate": 0.05},
        thresholds={"evidence_coverage": 0.8, "orphan_rate": 0.8},
    )
    assert hs.failing == ()
    assert hs.gate_passed is True
    assert all(c.healthy for c in hs.components)


def test_unknown_metric_key_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        kg_health_score({"totally_unknown_metric": 0.5})


def test_score_always_within_bounds() -> None:
    for metrics in (
        {"evidence_coverage": 0.0},
        {"evidence_coverage": 1.0},
        {"evidence_coverage": 0.3, "orphan_rate": 0.7, "contradiction_rate": 0.4},
        {"orphan_rate": 0.5, "duplicate_rate": 0.5},
    ):
        hs = kg_health_score(metrics)
        assert 0.0 <= hs.score <= 100.0


def test_as_dict_components_is_a_list() -> None:
    hs = kg_health_score({"evidence_coverage": 0.9, "orphan_rate": 0.1})
    d = hs.as_dict()
    assert isinstance(d["components"], list)
    assert all(isinstance(c, dict) for c in d["components"])
    assert d["grade"] == hs.grade
    assert d["score"] == round(hs.score, 4)


def test_component_as_dict_shape() -> None:
    hs = kg_health_score({"evidence_coverage": 0.5})
    comp = hs.components[0]
    assert isinstance(comp, Component)
    assert comp.as_dict() == {
        "name": "evidence_coverage",
        "raw": 0.5,
        "weight": 3.0,
        "contribution": 1.5,
        "healthy": True,
    }


def test_weighted_mean_partial_scorecard() -> None:
    # coverage=1.0 (w3), orphan_rate=1.0 -> effective 0.0 (w2).
    # score = 100 * (3.0 + 0.0) / (3.0 + 2.0) = 60.0.
    hs = kg_health_score({"evidence_coverage": 1.0, "orphan_rate": 1.0})
    assert hs.score == 60.0
    assert hs.grade == "C"


def test_lower_is_better_membership_and_defaults() -> None:
    assert "orphan_rate" in LOWER_IS_BETTER
    assert "duplicate_rate" in LOWER_IS_BETTER
    assert "contradiction_rate" in LOWER_IS_BETTER
    assert "evidence_coverage" not in LOWER_IS_BETTER
    assert DEFAULT_WEIGHTS["evidence_coverage"] > 0.0


def test_healthscore_is_frozen() -> None:
    hs = kg_health_score({"evidence_coverage": 1.0})
    with pytest.raises(AttributeError):
        hs.score = 0.0  # type: ignore[misc]
    assert isinstance(hs, HealthScore)

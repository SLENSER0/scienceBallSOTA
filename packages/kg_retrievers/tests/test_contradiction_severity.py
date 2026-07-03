"""Tests for the §15.4 contradiction severity classifier."""

from __future__ import annotations

import pytest

from kg_retrievers.contradiction_severity import (
    ContradictionSeverity,
    classify_contradiction,
    property_criticality,
)


def test_large_diff_critical_property_is_critical() -> None:
    # (1) relative_diff 0.8 on a criticality-1.0 property -> score 0.8, 'critical'.
    table = {"default": 0.5, "yield_strength": 1.0}
    result = classify_contradiction(
        {"relative_diff": 0.8, "property": "yield_strength"},
        criticality_table=table,
    )
    assert result.criticality == 1.0
    assert result.score == 0.8
    assert result.label == "critical"


def test_small_diff_is_low() -> None:
    # (2) relative_diff 0.05 -> label 'low'.
    result = classify_contradiction({"relative_diff": 0.05, "property": "color"})
    # score = 0.05 * (0.5 + 0.5*0.5) = 0.0375 -> low.
    assert result.score == pytest.approx(0.0375)
    assert result.label == "low"


def test_overlap_forces_low() -> None:
    # (3) overlap True forces 'low' even for a large relative_diff.
    table = {"default": 0.5, "yield_strength": 1.0}
    result = classify_contradiction(
        {"relative_diff": 0.9, "property": "yield_strength", "overlap": True},
        criticality_table=table,
    )
    assert result.label == "low"
    # The score itself is still computed (0.9 * 1.0), only the label is capped.
    assert result.score == 0.9


def test_unknown_property_uses_default_criticality() -> None:
    # (4) unknown property uses criticality 0.5.
    assert property_criticality("never_seen") == 0.5
    result = classify_contradiction({"relative_diff": 0.4, "property": "never_seen"})
    assert result.criticality == 0.5
    # score = 0.4 * (0.5 + 0.25) = 0.3 -> medium.
    assert result.score == pytest.approx(0.3)
    assert result.label == "medium"


def test_score_is_clamped_to_unit_interval() -> None:
    # (5) score is clamped to [0, 1] even for out-of-range relative_diff.
    table = {"default": 1.0}
    result = classify_contradiction(
        {"relative_diff": 5.0, "property": "x"}, criticality_table=table
    )
    assert result.relative_diff == 1.0
    assert result.score == 1.0
    assert 0.0 <= result.score <= 1.0
    assert result.label == "critical"


def test_criticality_table_override_changes_score() -> None:
    # (6) a criticality_table override changes the score.
    c = {"relative_diff": 0.5, "property": "stiffness"}
    low = classify_contradiction(c, criticality_table={"default": 0.0})
    high = classify_contradiction(c, criticality_table={"default": 0.0, "stiffness": 1.0})
    # low: 0.5 * (0.5 + 0) = 0.25 ; high: 0.5 * 1.0 = 0.5.
    assert low.score == 0.25
    assert high.score == 0.5
    assert high.score != low.score


def test_missing_relative_diff_defaults_to_zero_low() -> None:
    # (7) missing relative_diff defaults to 0.0 -> low.
    result = classify_contradiction({"property": "yield_strength"})
    assert result.relative_diff == 0.0
    assert result.score == 0.0
    assert result.label == "low"


def test_as_dict_round_trips_all_four_fields() -> None:
    # (8) as_dict() round-trips all four fields.
    result = classify_contradiction(
        {"relative_diff": 0.8, "property": "p"}, criticality_table={"default": 1.0}
    )
    d = result.as_dict()
    assert d == {
        "label": result.label,
        "score": result.score,
        "relative_diff": result.relative_diff,
        "criticality": result.criticality,
    }
    rebuilt = ContradictionSeverity(**d)
    assert rebuilt == result

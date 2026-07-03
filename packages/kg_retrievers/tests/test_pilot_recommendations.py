"""Tests for the «что проверить пилотно» selection layer (§24.11)."""

from __future__ import annotations

from kg_retrievers.pilot_recommendations import (
    REASON_BOTH,
    REASON_LOCAL_DEPENDENCE,
    REASON_LOW_CONFIDENCE,
    PilotRecommendation,
    recommend_pilots,
)


def _cond(condition_id: str, confidence: float, local_dependence: bool) -> dict:
    return {
        "condition_id": condition_id,
        "confidence": confidence,
        "local_dependence": local_dependence,
    }


def test_both_triggers_priority_2_reason_both() -> None:
    # (1) confidence 0.3 (< 0.5) & local True → priority 2, reason both.
    recs = recommend_pilots([_cond("c1", 0.3, True)])
    assert len(recs) == 1
    assert recs[0] == PilotRecommendation("c1", REASON_BOTH, 2)


def test_high_conf_no_local_not_recommended() -> None:
    # (2) confidence 0.9 & local False → not recommended.
    recs = recommend_pilots([_cond("c1", 0.9, False)])
    assert recs == ()


def test_local_only_reason_and_priority() -> None:
    # (3) confidence 0.9 & local True → reason local_dependence, priority 1.
    recs = recommend_pilots([_cond("c1", 0.9, True)])
    assert len(recs) == 1
    assert recs[0].reason == REASON_LOCAL_DEPENDENCE
    assert recs[0].priority == 1


def test_two_priority_1_sorted_by_condition_id() -> None:
    # (4) two priority-1 items sort by condition_id ascending.
    recs = recommend_pilots(
        [
            _cond("zeta", 0.2, False),  # low_confidence, priority 1
            _cond("alpha", 0.9, True),  # local_dependence, priority 1
        ]
    )
    assert [r.condition_id for r in recs] == ["alpha", "zeta"]
    assert all(r.priority == 1 for r in recs)
    assert recs[0].reason == REASON_LOCAL_DEPENDENCE
    assert recs[1].reason == REASON_LOW_CONFIDENCE


def test_threshold_boundary_strict_less_than() -> None:
    # (5) confidence == 0.5 is NOT low (strict <); with local False → not recommended.
    assert recommend_pilots([_cond("c1", 0.5, False)]) == ()
    # ...but confidence just below the threshold IS low.
    recs = recommend_pilots([_cond("c1", 0.4999, False)])
    assert len(recs) == 1
    assert recs[0].reason == REASON_LOW_CONFIDENCE


def test_empty_input_empty_tuple() -> None:
    # (6) empty input → empty tuple.
    assert recommend_pilots([]) == ()


def test_as_dict_priority_is_int() -> None:
    # (7) as_dict()['priority'] is a plain int.
    rec = recommend_pilots([_cond("c1", 0.3, True)])[0]
    d = rec.as_dict()
    assert d == {"condition_id": "c1", "reason": REASON_BOTH, "priority": 2}
    assert type(d["priority"]) is int


def test_priority_2_sorts_before_priority_1() -> None:
    # priority desc: a both-trigger (2) comes before any single-trigger (1).
    recs = recommend_pilots(
        [
            _cond("aaa", 0.9, True),  # local only, priority 1
            _cond("zzz", 0.1, True),  # both, priority 2
        ]
    )
    assert [(r.condition_id, r.priority) for r in recs] == [("zzz", 2), ("aaa", 1)]


def test_custom_threshold() -> None:
    # A stricter threshold flags a mid confidence that the default would pass.
    assert recommend_pilots([_cond("c1", 0.7, False)]) == ()
    recs = recommend_pilots([_cond("c1", 0.7, False)], conf_threshold=0.8)
    assert len(recs) == 1
    assert recs[0].reason == REASON_LOW_CONFIDENCE

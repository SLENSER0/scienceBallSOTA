"""Review-task priority + SLA aging (§16.4) — hand-checked pure-function tests."""

from __future__ import annotations

from itertools import pairwise

from kg_common.storage.review_priority import (
    CRITICAL_TASK_TYPES,
    PriorityInputs,
    age_hours,
    compute_priority,
    is_overdue,
)

# A neutral baseline: normal kind, evidence saturated to 0-contribution, degree 0.
# So only the confidence term drives the score => easy to hand-check.
_NORMAL = "low_confidence"
_CRITICAL = "conflicting"  # ∈ CRITICAL_TASK_TYPES


def test_priority_strictly_decreases_as_confidence_rises() -> None:
    # evidence=5 -> evidence_component 0; degree 0 -> score = (1-conf)*60
    scores = [
        compute_priority(PriorityInputs(c, _NORMAL, evidence_count=5, entity_degree=0))
        for c in (0.1, 0.3, 0.5, 0.7, 0.9)
    ]
    assert scores == [54, 42, 30, 18, 6]  # exact hand-computed values
    assert all(a > b for a, b in pairwise(scores))  # strictly ↓


def test_critical_type_boosts_over_normal() -> None:
    base = {"confidence": 0.5, "evidence_count": 5, "entity_degree": 0}
    normal = compute_priority(PriorityInputs(task_type=_NORMAL, **base))
    critical = compute_priority(PriorityInputs(task_type=_CRITICAL, **base))
    assert normal == 30  # (1-0.5)*60
    assert critical == 50  # 30 + CRITICAL_BOOST(20)
    assert critical > normal
    # every declared critical kind gets the same +20 boost
    for kind in CRITICAL_TASK_TYPES:
        assert compute_priority(PriorityInputs(task_type=kind, **base)) == 50


def test_fewer_evidence_gives_higher_priority() -> None:
    # confidence 0.5 -> base 30; evidence_component = max(0, 10 - n*2)
    scores = [
        compute_priority(PriorityInputs(0.5, _NORMAL, evidence_count=n, entity_degree=0))
        for n in (0, 1, 2, 3)
    ]
    assert scores == [40, 38, 36, 34]  # 30 + {10, 8, 6, 4}
    assert all(a > b for a, b in pairwise(scores))  # strictly ↓
    # evidence contribution saturates at 0 (5 and 10 evidence are equal)
    sat5 = compute_priority(PriorityInputs(0.5, _NORMAL, evidence_count=5, entity_degree=0))
    sat10 = compute_priority(PriorityInputs(0.5, _NORMAL, evidence_count=10, entity_degree=0))
    assert sat5 == sat10 == 30


def test_higher_degree_gives_higher_priority() -> None:
    # confidence 0.5 -> base 30 (evidence 5 -> 0); degree_component = min(10, d)
    scores = [
        compute_priority(PriorityInputs(0.5, _NORMAL, evidence_count=5, entity_degree=d))
        for d in (0, 3, 7)
    ]
    assert scores == [30, 33, 37]
    assert all(a < b for a, b in pairwise(scores))  # strictly ↑
    # degree contribution saturates at 10 (degree 10 and 20 are equal)
    hi10 = compute_priority(PriorityInputs(0.5, _NORMAL, evidence_count=5, entity_degree=10))
    hi20 = compute_priority(PriorityInputs(0.5, _NORMAL, evidence_count=5, entity_degree=20))
    assert hi10 == hi20 == 40


def test_priority_is_bounded_1_to_100() -> None:
    # worst case: no confidence, critical, no evidence, huge degree -> exactly 100
    worst = compute_priority(PriorityInputs(0.0, _CRITICAL, evidence_count=0, entity_degree=1000))
    assert worst == 100  # 60 + 20 + 10 + 10, clamped at ceiling (not over)
    # best case: full confidence, normal, lots of evidence, no degree -> clamped to 1
    best = compute_priority(PriorityInputs(1.0, _NORMAL, evidence_count=1000, entity_degree=0))
    assert best == 1  # raw 0, floored to PRIORITY_MIN
    # out-of-range confidence is clamped, negatives treated as 0 -> still in band
    for inp in (
        PriorityInputs(-5.0, _CRITICAL, evidence_count=-3, entity_degree=-9),
        PriorityInputs(9.9, _NORMAL, evidence_count=0, entity_degree=0),
    ):
        assert 1 <= compute_priority(inp) <= 100


def test_age_hours_between_two_iso_stamps() -> None:
    assert age_hours("2026-01-01T00:00:00", "2026-01-01T02:30:00") == 2.5
    assert age_hours("2026-01-01T00:00:00", "2026-01-02T00:00:00") == 24.0
    # now before created => negative age
    assert age_hours("2026-01-01T06:00:00", "2026-01-01T00:00:00") == -6.0
    # naive vs +00:00 offset compared as UTC (no tz-mismatch error)
    assert age_hours("2026-01-01T00:00:00", "2026-01-01T03:00:00+00:00") == 3.0


def test_is_overdue_true_past_sla() -> None:
    # 25h old with a 24h SLA -> overdue
    assert is_overdue("2026-01-01T00:00:00", "2026-01-02T01:00:00", sla_hours=24.0) is True


def test_is_overdue_false_within_and_at_sla() -> None:
    # 12h old, 24h SLA -> within
    assert is_overdue("2026-01-01T00:00:00", "2026-01-01T12:00:00", sla_hours=24.0) is False
    # exactly at the deadline (24h, 24h SLA) is still within SLA (strict >)
    assert is_overdue("2026-01-01T00:00:00", "2026-01-02T00:00:00", sla_hours=24.0) is False


def test_compute_priority_is_deterministic() -> None:
    inp = PriorityInputs(0.42, _CRITICAL, evidence_count=2, entity_degree=4)
    first = compute_priority(inp)
    assert first == compute_priority(inp)  # same inputs -> same output
    # (1-0.42)*60=34.8 +20 critical +max(0,10-2*2)=6 +min(10,4)=4 = 64.8 → round 65
    assert first == 65


def test_priority_inputs_as_dict_roundtrips() -> None:
    inp = PriorityInputs(0.3, _NORMAL, evidence_count=2, entity_degree=5)
    assert inp.as_dict() == {
        "confidence": 0.3,
        "task_type": "low_confidence",
        "evidence_count": 2,
        "entity_degree": 5,
    }
    assert PriorityInputs(**inp.as_dict()) == inp  # frozen dataclass equality

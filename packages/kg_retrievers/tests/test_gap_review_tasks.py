"""Tests for §15.4 / §15.7 / §12.1 review-task payloads (pure python, no store)."""

from __future__ import annotations

from kg_retrievers.gap_review_tasks import (
    CRITICAL_GAP_TYPES,
    ReviewTask,
    build_review_tasks,
    contradiction_to_task,
    gap_to_task,
)


def test_high_severity_unverified_claim_gap_yields_high_gap_task() -> None:
    """(1) severity='high' unverified_claim -> kind=='gap', priority=='high'."""
    task = gap_to_task(
        {
            "gap_type": "unverified_claim",
            "severity": "high",
            "subject_id": "claim:42",
            "evidence_ids": ["e1", "e2"],
        }
    )
    assert task is not None
    assert task.kind == "gap"
    assert task.priority == "high"
    assert task.subject_id == "claim:42"
    assert task.gap_type == "unverified_claim"


def test_non_critical_gap_type_returns_none() -> None:
    """(2) missing_baseline is not a critical gap_type -> None."""
    assert "missing_baseline" not in CRITICAL_GAP_TYPES
    assert gap_to_task({"gap_type": "missing_baseline", "severity": "high"}) is None


def test_low_severity_critical_gap_returns_none() -> None:
    """(3) a critical-type gap with severity='low' is dropped -> None."""
    assert gap_to_task({"gap_type": "missing_source_span", "severity": "low"}) is None


def test_contradiction_priority_from_relative_diff() -> None:
    """(4) relative_diff 0.6 -> 'high', 0.1 -> 'low'."""
    high = contradiction_to_task({"subject_id": "s1", "relative_diff": 0.6})
    low = contradiction_to_task({"subject_id": "s2", "relative_diff": 0.1})
    assert high.kind == "contradiction"
    assert high.priority == "high"
    assert low.priority == "low"
    # boundary: exactly 0.5 is high, exactly 0.2 is medium.
    assert contradiction_to_task({"relative_diff": 0.5}).priority == "high"
    assert contradiction_to_task({"relative_diff": 0.2}).priority == "medium"
    # contradictions never carry a gap_type.
    assert high.gap_type is None


def test_identical_gaps_collapse_to_one_task() -> None:
    """(5) two identical gaps de-dupe by (kind, subject_id, gap_type)."""
    gap = {
        "gap_type": "unverified_claim",
        "severity": "high",
        "subject_id": "claim:7",
        "evidence_ids": ["e1"],
    }
    tasks = build_review_tasks([dict(gap), dict(gap)], [])
    assert len(tasks) == 1
    assert tasks[0].subject_id == "claim:7"


def test_evidence_ids_carried_through() -> None:
    """(6) evidence_ids are carried through from the source dict (as str, in order)."""
    ev = ["ev-a", "ev-b", "ev-c"]
    task = gap_to_task(
        {"gap_type": "missing_source_span", "severity": "medium", "evidence_ids": ev}
    )
    assert task is not None
    assert task.evidence_ids == ev
    contra = contradiction_to_task({"relative_diff": 0.9, "evidence_ids": ev})
    assert contra.evidence_ids == ev


def test_task_id_deterministic_for_same_input() -> None:
    """(7) task_id is deterministic for the same input; evidence order-invariant."""
    a = gap_to_task(
        {
            "gap_type": "unverified_claim",
            "severity": "high",
            "subject_id": "x",
            "evidence_ids": ["e1", "e2"],
        }
    )
    b = gap_to_task(
        {
            "gap_type": "unverified_claim",
            "severity": "high",
            "subject_id": "x",
            "evidence_ids": ["e2", "e1"],
        }
    )
    assert a is not None and b is not None
    assert a.task_id == b.task_id
    # a different subject changes the id.
    c = gap_to_task({"gap_type": "unverified_claim", "severity": "high", "subject_id": "y"})
    assert c is not None
    assert c.task_id != a.task_id


def test_as_dict_exposes_all_seven_fields() -> None:
    """(8) as_dict() exposes all seven ReviewTask fields."""
    task = ReviewTask(
        task_id="task:gap:abc",
        kind="gap",
        priority="high",
        subject_id="s",
        gap_type="unverified_claim",
        evidence_ids=["e1"],
        reason="critical field missing",
    )
    d = task.as_dict()
    assert set(d) == {
        "task_id",
        "kind",
        "priority",
        "subject_id",
        "gap_type",
        "evidence_ids",
        "reason",
    }
    assert d["evidence_ids"] == ["e1"]
    assert d["gap_type"] == "unverified_claim"


def test_build_orders_gaps_then_contradictions_and_dedupes_both() -> None:
    """build_review_tasks emits gap tasks first, then contradictions, deduped."""
    gaps = [
        {"gap_type": "unverified_claim", "severity": "high", "subject_id": "g1"},
        {"gap_type": "missing_baseline", "severity": "high", "subject_id": "g2"},
    ]
    contras = [
        {"subject_id": "c1", "relative_diff": 0.7},
        {"subject_id": "c1", "relative_diff": 0.7},
    ]
    tasks = build_review_tasks(gaps, contras)
    assert [t.kind for t in tasks] == ["gap", "contradiction"]
    assert [t.subject_id for t in tasks] == ["g1", "c1"]
    assert tasks[0].reason == "critical field missing"
    assert tasks[1].reason == "claim contradicts existing claim"

"""Auto-resolve stale review tasks (§16.4) — hand-checked pure-function tests."""

from __future__ import annotations

from kg_common.storage.review_autoresolve import (
    AutoResolveDecision,
    evaluate_task,
    scan,
)


def test_missing_critical_field_all_present_resolves() -> None:
    # (1) every named field is now present + non-null -> resolve True
    task = {
        "task_id": "t1",
        "task_type": "missing_critical_field",
        "status": "open",
        "payload": {"missing_fields": ["unit", "value"]},
    }
    state = {"unit": "kg", "value": 3.2}
    decision = evaluate_task(task, state)
    assert decision.resolve is True
    assert "all fields present" in decision.reason


def test_missing_critical_field_one_still_missing_does_not_resolve() -> None:
    # (2) one field still missing/null -> resolve False
    task = {
        "task_id": "t2",
        "task_type": "missing_critical_field",
        "status": "open",
        "payload": {"missing_fields": ["unit", "value"]},
    }
    # 'value' present but null -> counts as still missing
    state = {"unit": "kg", "value": None}
    decision = evaluate_task(task, state)
    assert decision.resolve is False
    assert "still missing" in decision.reason
    assert "value" in decision.reason  # (7) names the offending field


def test_low_confidence_above_threshold_resolves() -> None:
    # (3) 0.7 >= 0.65 -> resolve True
    task = {
        "task_id": "t3",
        "task_type": "low_confidence",
        "status": "in_review",
        "payload": {"threshold": 0.65},
    }
    decision = evaluate_task(task, {"confidence": 0.7})
    assert decision.resolve is True
    assert "0.7" in decision.reason and "0.65" in decision.reason  # (7)


def test_low_confidence_below_threshold_does_not_resolve() -> None:
    task = {
        "task_id": "t3b",
        "task_type": "low_confidence",
        "status": "open",
        "payload": {"threshold": 0.65},
    }
    assert evaluate_task(task, {"confidence": 0.6}).resolve is False


def test_contradiction_target_resolved_resolves() -> None:
    # (4) target status 'resolved' -> resolve True
    task = {"task_id": "t4", "task_type": "contradiction", "status": "open"}
    decision = evaluate_task(task, {"status": "resolved"})
    assert decision.resolve is True
    assert "resolved" in decision.reason  # (7)
    # still open on the target -> stays open
    assert evaluate_task(task, {"status": "open"}).resolve is False


def test_ambiguous_er_decision_resolved_resolves() -> None:
    task = {"task_id": "t5", "task_type": "ambiguous_er", "status": "open"}
    assert evaluate_task(task, {"decision": "resolved"}).resolve is True
    assert evaluate_task(task, {"decision": "pending"}).resolve is False


def test_low_quality_ocr_never_auto_resolves() -> None:
    # (5) an unmodelled type never auto-resolves, even with a rich state
    task = {
        "task_id": "t6",
        "task_type": "low_quality_ocr",
        "status": "open",
        "payload": {"threshold": 0.0},
    }
    decision = evaluate_task(task, {"confidence": 1.0, "status": "resolved"})
    assert decision.resolve is False
    assert "not auto-resolvable" in decision.reason  # (7)


def test_scan_skips_already_resolved_task() -> None:
    # (6) a task with status 'resolved' is skipped even though its defect cleared
    closed = {
        "task_id": "done",
        "task_type": "contradiction",
        "status": "resolved",
    }
    open_task = {
        "task_id": "live",
        "task_type": "contradiction",
        "status": "open",
    }
    states = {
        "done": {"status": "resolved"},
        "live": {"status": "resolved"},
    }
    decisions = scan([closed, open_task], states)
    ids = [d.task_id for d in decisions]
    assert ids == ["live"]  # closed task skipped, live one auto-resolves


def test_scan_returns_only_resolvable_open_tasks() -> None:
    tasks = [
        {  # resolves
            "task_id": "a",
            "task_type": "low_confidence",
            "status": "open",
            "payload": {"threshold": 0.5},
        },
        {  # open but defect still holds -> not returned
            "task_id": "b",
            "task_type": "low_confidence",
            "status": "in_review",
            "payload": {"threshold": 0.9},
        },
        {  # in_review, no state -> not returned
            "task_id": "c",
            "task_type": "missing_critical_field",
            "status": "in_review",
            "payload": {"missing_fields": ["x"]},
        },
    ]
    states = {"a": {"confidence": 0.6}, "b": {"confidence": 0.6}}
    decisions = scan(tasks, states)
    assert [d.task_id for d in decisions] == ["a"]
    assert all(d.resolve for d in decisions)


def test_as_dict_round_trips() -> None:
    # (8) as_dict -> **d -> AutoResolveDecision reconstructs the same object
    original = AutoResolveDecision(task_id="z", resolve=True, reason="because")
    d = original.as_dict()
    assert d == {"task_id": "z", "resolve": True, "reason": "because"}
    assert AutoResolveDecision(**d) == original

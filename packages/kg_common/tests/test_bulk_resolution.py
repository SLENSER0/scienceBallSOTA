"""Tests for the §16.9 bulk resolution planner (RU/EN)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_common.storage.bulk_resolution import BulkPlan, is_applicable, plan_bulk


def _task(task_id: str, status: str, task_type: str, target_id: str | None = None) -> dict:
    t: dict = {"task_id": task_id, "status": status, "task_type": task_type}
    if target_id is not None:
        t["target_id"] = target_id
    return t


def test_two_open_low_confidence_both_applicable() -> None:
    """(1) two open low_confidence tasks, action 'accept' -> both applicable."""
    tasks = [
        _task("t1", "open", "low_confidence", "e1"),
        _task("t2", "open", "low_confidence", "e2"),
    ]
    plan = plan_bulk(tasks, "accept", ["low_confidence"])
    assert plan.applicable == ["t1", "t2"]
    assert plan.skipped == {}


def test_resolved_task_skipped_closed() -> None:
    """(2) a resolved task -> skipped with reason 'closed'."""
    tasks = [_task("t1", "resolved", "low_confidence", "e1")]
    plan = plan_bulk(tasks, "accept", ["low_confidence"])
    assert plan.applicable == []
    assert plan.skipped == {"t1": "closed"}


def test_contradiction_skipped_type_not_allowed() -> None:
    """(3) contradiction task when only low_confidence allowed -> 'type_not_allowed'."""
    tasks = [_task("t1", "open", "contradiction", "e1")]
    plan = plan_bulk(tasks, "accept", ["low_confidence"])
    assert plan.applicable == []
    assert plan.skipped == {"t1": "type_not_allowed"}


def test_duplicate_target_id_appears_once() -> None:
    """(4) duplicate target_id across two applicable tasks appears once."""
    tasks = [
        _task("t1", "open", "low_confidence", "shared"),
        _task("t2", "in_review", "low_confidence", "shared"),
    ]
    plan = plan_bulk(tasks, "accept", ["low_confidence"])
    assert plan.applicable == ["t1", "t2"]
    assert plan.target_ids == ["shared"]


def test_target_ids_follow_first_occurrence_order() -> None:
    """(5) order of target_ids follows first occurrence."""
    tasks = [
        _task("t1", "open", "low_confidence", "eB"),
        _task("t2", "open", "low_confidence", "eA"),
        _task("t3", "open", "low_confidence", "eB"),
        _task("t4", "open", "low_confidence", "eC"),
    ]
    plan = plan_bulk(tasks, "accept", ["low_confidence"])
    assert plan.target_ids == ["eB", "eA", "eC"]


def test_empty_tasks_gives_empty_plan() -> None:
    """(6) empty tasks -> empty applicable and empty target_ids."""
    plan = plan_bulk([], "accept", ["low_confidence"])
    assert plan.applicable == []
    assert plan.target_ids == []
    assert plan.skipped == {}


def test_as_dict_skipped_is_dict() -> None:
    """(7) as_dict()['skipped'] is a dict."""
    tasks = [
        _task("t1", "open", "low_confidence", "e1"),
        _task("t2", "resolved", "low_confidence", "e2"),
    ]
    plan = plan_bulk(tasks, "accept", ["low_confidence"])
    d = plan.as_dict()
    assert isinstance(d["skipped"], dict)
    assert d["skipped"] == {"t2": "closed"}
    assert d["action"] == "accept"
    assert d["applicable"] == ["t1"]
    assert d["target_ids"] == ["e1"]


def test_is_applicable_helper() -> None:
    """is_applicable mirrors the status+type gate used by plan_bulk."""
    assert is_applicable(_task("t1", "open", "low_confidence"), ["low_confidence"])
    assert is_applicable(_task("t1", "in_review", "low_confidence"), ["low_confidence"])
    assert not is_applicable(_task("t1", "resolved", "low_confidence"), ["low_confidence"])
    assert not is_applicable(_task("t1", "open", "contradiction"), ["low_confidence"])


def test_multiple_allowed_types() -> None:
    """Both allowed types pass; a third type is skipped."""
    tasks = [
        _task("t1", "open", "low_confidence", "e1"),
        _task("t2", "open", "contradiction", "e2"),
        _task("t3", "open", "duplicate", "e3"),
    ]
    plan = plan_bulk(tasks, "accept", ["low_confidence", "contradiction"])
    assert plan.applicable == ["t1", "t2"]
    assert plan.skipped == {"t3": "type_not_allowed"}
    assert plan.target_ids == ["e1", "e2"]


def test_frozen_dataclass() -> None:
    """BulkPlan is immutable (frozen)."""
    plan = plan_bulk([], "accept", ["low_confidence"])
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.action = "reject"  # type: ignore[misc]


def test_returns_bulk_plan_instance() -> None:
    plan = plan_bulk([], "accept", ["low_confidence"])
    assert isinstance(plan, BulkPlan)

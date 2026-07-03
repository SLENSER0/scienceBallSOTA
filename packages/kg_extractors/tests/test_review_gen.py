"""Tests for §16.5 auto-generation of review tasks — hand-checked specs.

Review routing reuses §6.15 :func:`route_extraction` with defaults
(auto_accept_at=0.85, reject_at=0.2): only ``review`` items become tasks.
0.3 confidence → review (mid band, priority 0.7); 0.95 clean → auto_accept (no
task); 0.1 clean → reject (no task). Escalation flags force a ``flag_review``.
"""

from __future__ import annotations

import pytest

from kg_extractors.review_gen import (
    KIND_CONFIDENCE_REVIEW,
    KIND_FLAG_REVIEW,
    KIND_SCHEMA_CHANGE,
    SCHEMA_TERM_PRIORITY,
    ReviewTaskSpec,
    generate_review_tasks,
    new_schema_term_task,
)
from kg_extractors.review_routing import route_extraction


def test_low_confidence_item_becomes_review_task() -> None:
    """A 0.3-confidence fact routes to review → one confidence_review task (§16.5)."""
    items = [{"target_id": "M1", "confidence": 0.3, "unit": "MPa", "value": 500}]
    tasks = generate_review_tasks(items)
    assert len(tasks) == 1
    task = tasks[0]
    assert isinstance(task, ReviewTaskSpec)
    assert task.target_id == "M1"
    assert task.kind == KIND_CONFIDENCE_REVIEW
    assert task.dedup_key == "M1:confidence_review"
    # priority = 1 - 0.3 = 0.7 (hand-checked, copied from the router).
    assert task.priority == 0.7
    assert "mid_confidence" in task.reason


def test_high_confidence_item_yields_no_task() -> None:
    """A clean 0.95 fact auto-accepts → no review task (§16.5)."""
    items = [{"target_id": "M2", "confidence": 0.95, "unit": "MPa", "value": 500}]
    assert generate_review_tasks(items) == []


def test_reject_item_yields_no_task() -> None:
    """A clean 0.1 fact rejects (not review) → no task; only review mints (§16.5)."""
    items = [{"target_id": "M3", "confidence": 0.1, "unit": "MPa", "value": 500}]
    assert generate_review_tasks(items) == []


def test_flagged_item_becomes_flag_review_with_reason() -> None:
    """An out_of_range flag at 0.95 forces review → flag_review carrying the flag (§7.7)."""
    items = [{"target_id": "M4", "confidence": 0.95, "value": 9e9, "flags": ["out_of_range"]}]
    tasks = generate_review_tasks(items)
    assert len(tasks) == 1
    task = tasks[0]
    assert task.kind == KIND_FLAG_REVIEW
    assert task.dedup_key == "M4:flag_review"
    assert "out_of_range" in task.reason


def test_priority_copied_verbatim_from_router() -> None:
    """Task priority equals the router's queue priority for the same item (§16.5)."""
    item = {"target_id": "M5", "confidence": 0.4, "unit": "MPa", "value": 500}
    expected = route_extraction(item).priority
    task = generate_review_tasks([item])[0]
    assert task.priority == expected
    # hand-checked: 1 - 0.4 = 0.6.
    assert task.priority == 0.6


def test_dedup_collapses_same_target_and_kind_keeping_highest_priority() -> None:
    """Two review facts on M6 (same kind) collapse to one task, keeping urgent (§16.5)."""
    items = [
        {"target_id": "M6", "confidence": 0.6, "unit": "MPa", "value": 500},  # priority 0.4
        {"target_id": "M6", "confidence": 0.3, "unit": "MPa", "value": 500},  # priority 0.7
    ]
    tasks = generate_review_tasks(items)
    assert len(tasks) == 1
    assert tasks[0].dedup_key == "M6:confidence_review"
    # dedup keeps the shakiest (higher-priority) representative.
    assert tasks[0].priority == 0.7


def test_dedup_key_is_stable_and_derived_from_target_and_kind() -> None:
    """dedup_key is exactly f"{target_id}:{kind}" for the minted task (§16.5)."""
    task = generate_review_tasks([{"id": "X9", "confidence": 0.5, "value": 1, "unit": "K"}])[0]
    assert task.dedup_key == f"{task.target_id}:{task.kind}"
    assert task.dedup_key == "X9:confidence_review"


def test_tasks_sorted_by_descending_priority() -> None:
    """Multiple tasks head with the highest-priority (lowest-confidence) fact (§16.5)."""
    items = [
        {"target_id": "A", "confidence": 0.7, "unit": "MPa", "value": 500},  # priority 0.3
        {"target_id": "B", "confidence": 0.25, "unit": "MPa", "value": 500},  # priority 0.75
        {"target_id": "C", "confidence": 0.5, "unit": "MPa", "value": 500},  # priority 0.5
    ]
    tasks = generate_review_tasks(items)
    assert [t.target_id for t in tasks] == ["B", "C", "A"]
    assert [t.priority for t in tasks] == [0.75, 0.5, 0.3]


def test_thresholds_passed_through_to_router() -> None:
    """Custom thresholds flip a 0.7 fact from review (default) to auto-accept (§16.5)."""
    item = {"target_id": "M7", "confidence": 0.7, "unit": "MPa", "value": 500}
    assert len(generate_review_tasks([item])) == 1  # 0.7 reviews under defaults
    assert generate_review_tasks([item], thresholds={"auto_accept_at": 0.6}) == []


def test_new_schema_term_task_builds_schema_change_spec() -> None:
    """new_schema_term_task mints a schema_change task keyed on the term (§12.1)."""
    task = new_schema_term_task("bandgap_narrowing")
    assert isinstance(task, ReviewTaskSpec)
    assert task.target_id == "bandgap_narrowing"
    assert task.kind == KIND_SCHEMA_CHANGE
    assert task.dedup_key == "bandgap_narrowing:schema_change"
    assert task.priority == SCHEMA_TERM_PRIORITY
    assert "bandgap_narrowing" in task.reason


def test_new_schema_term_task_rejects_blank_term() -> None:
    """A blank schema term is rejected (§12.1)."""
    with pytest.raises(ValueError):
        new_schema_term_task("   ")


def test_empty_items_returns_empty_list() -> None:
    """No items → no tasks (§16.5)."""
    assert generate_review_tasks([]) == []


def test_as_dict_exposes_all_fields() -> None:
    """ReviewTaskSpec.as_dict() carries the full field set (§16.5)."""
    task = new_schema_term_task("new_prop")
    out = task.as_dict()
    assert set(out) == {"target_id", "kind", "priority", "reason", "dedup_key"}
    assert out["kind"] == KIND_SCHEMA_CHANGE
    assert out["dedup_key"] == "new_prop:schema_change"

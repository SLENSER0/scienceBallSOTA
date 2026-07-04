"""Review-task queue store (§16.4 review queue: priorities, dedup, assignment)."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

from kg_common.storage.review_queue import (
    STATUS_IN_REVIEW,
    STATUS_RESOLVED,
    ReviewQueue,
    ReviewTask,
)


@pytest.fixture
def queue() -> ReviewQueue:
    q = ReviewQueue("sqlite:///:memory:")
    q.migrate()
    return q


def test_enqueue_and_next_ordered_by_priority(queue: ReviewQueue) -> None:
    # enqueue out of order; next_tasks must return highest priority first
    queue.enqueue(ReviewTask("t:low", priority=0.2, dedup_key="d1"))
    queue.enqueue(ReviewTask("t:high", priority=0.9, dedup_key="d2"))
    queue.enqueue(ReviewTask("t:mid", priority=0.5, dedup_key="d3"))
    ordered = [t.task_id for t in queue.next_tasks()]
    assert ordered == ["t:high", "t:mid", "t:low"]


def test_dedup_by_key_keeps_one_higher_priority_wins(queue: ReviewQueue) -> None:
    # same dedup_key, different task_id: single row survives, priority = max
    queue.enqueue(ReviewTask("t:1", target_id="ent:A", priority=0.3, dedup_key="dup"))
    queue.enqueue(ReviewTask("t:2", target_id="ent:A", priority=0.8, dedup_key="dup"))
    tasks = queue.next_tasks()
    assert len(tasks) == 1
    assert tasks[0].task_id == "t:1"  # first task kept (idempotent by dedup_key)
    assert tasks[0].priority == 0.8  # priority raised to the max
    # a lower re-enqueue must NOT lower the priority
    queue.enqueue(ReviewTask("t:3", target_id="ent:A", priority=0.1, dedup_key="dup"))
    tasks = queue.next_tasks()
    assert len(tasks) == 1 and tasks[0].priority == 0.8


def test_assign_sets_assignee_and_status(queue: ReviewQueue) -> None:
    queue.enqueue(ReviewTask("t:1", priority=0.5, dedup_key="d1"))
    queue.assign("t:1", "reviewer:anna")
    got = queue.get("t:1")
    assert got is not None
    assert got.assignee == "reviewer:anna"
    assert got.status == STATUS_IN_REVIEW
    # assigned (in_review) task leaves the open worklist
    assert queue.next_tasks() == []


def test_resolve_removes_from_open(queue: ReviewQueue) -> None:
    queue.enqueue(ReviewTask("t:1", priority=0.5, dedup_key="d1"))
    queue.enqueue(ReviewTask("t:2", priority=0.4, dedup_key="d2"))
    queue.resolve("t:1")
    open_ids = [t.task_id for t in queue.next_tasks()]
    assert open_ids == ["t:2"]
    assert queue.get("t:1").status == STATUS_RESOLVED


def test_counts_by_status(queue: ReviewQueue) -> None:
    queue.enqueue(ReviewTask("t:1", priority=0.5, dedup_key="d1"))
    queue.enqueue(ReviewTask("t:2", priority=0.4, dedup_key="d2"))
    queue.enqueue(ReviewTask("t:3", priority=0.3, dedup_key="d3"))
    queue.assign("t:2", "reviewer:bob")  # -> in_review
    queue.resolve("t:3")  # -> resolved
    assert queue.counts_by_status() == {"open": 1, "in_review": 1, "resolved": 1}


def test_next_filters_by_assignee(queue: ReviewQueue) -> None:
    # open tasks may be pre-assigned to a reviewer's worklist
    queue.enqueue(ReviewTask("t:a1", priority=0.9, assignee="anna", dedup_key="d1"))
    queue.enqueue(ReviewTask("t:a2", priority=0.7, assignee="anna", dedup_key="d2"))
    queue.enqueue(ReviewTask("t:b1", priority=0.8, assignee="bob", dedup_key="d3"))
    anna = [t.task_id for t in queue.next_tasks(assignee="anna")]
    assert anna == ["t:a1", "t:a2"]  # only anna's, still priority-ordered
    bob = [t.task_id for t in queue.next_tasks(assignee="bob")]
    assert bob == ["t:b1"]
    # no filter returns the whole open pool
    assert len(queue.next_tasks()) == 3


def test_empty_queue(queue: ReviewQueue) -> None:
    assert queue.next_tasks() == []
    assert queue.counts_by_status() == {}
    assert queue.get("nope") is None


def test_next_tasks_respects_limit(queue: ReviewQueue) -> None:
    for i in range(5):
        queue.enqueue(ReviewTask(f"t:{i}", priority=float(i), dedup_key=f"d{i}"))
    top2 = [t.task_id for t in queue.next_tasks(limit=2)]
    assert top2 == ["t:4", "t:3"]  # two highest priorities only


def test_migrate_creates_queue_polling_indexes(queue: ReviewQueue) -> None:
    # perf-opt: migrate() must build the composite indexes that serve the
    # open-queue ordering and the per-reviewer worklist filter.
    idx = {i["name"] for i in inspect(queue.engine).get_indexes("review_tasks")}
    assert "ix_review_tasks_status_priority" in idx
    assert "ix_review_tasks_assignee_status" in idx


def test_status_priority_index_columns(queue: ReviewQueue) -> None:
    # the ordering index must cover status (equality) then the sort keys, in the
    # exact order next_tasks() filters/sorts on.
    by_name = {i["name"]: i for i in inspect(queue.engine).get_indexes("review_tasks")}
    cols = by_name["ix_review_tasks_status_priority"]["column_names"]
    assert cols == ["status", "priority", "created_at", "task_id"]


def test_ordering_unchanged_with_index(queue: ReviewQueue) -> None:
    # behavior-preserving: identical results to the pre-index query. Mix
    # equal-priority tasks so the created_at/task_id tiebreakers exercise too.
    queue.enqueue(ReviewTask("t:a", priority=0.5, created_at="2026-01-01", dedup_key="d1"))
    queue.enqueue(ReviewTask("t:c", priority=0.5, created_at="2026-01-02", dedup_key="d2"))
    queue.enqueue(ReviewTask("t:b", priority=0.5, created_at="2026-01-02", dedup_key="d3"))
    queue.enqueue(ReviewTask("t:top", priority=0.9, created_at="2026-01-03", dedup_key="d4"))
    ordered = [t.task_id for t in queue.next_tasks()]
    # priority desc, then created_at asc, then task_id asc as the final tiebreak
    assert ordered == ["t:top", "t:a", "t:b", "t:c"]

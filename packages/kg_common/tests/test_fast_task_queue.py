"""Fast background task queue tests (§9.10).

Hand-checked: every priority pick, FIFO tie-break, retry count, and dead-letter
transition is spelled out against the spec assertions.
"""

from __future__ import annotations

import pytest

from kg_common.fast_task_queue import FastTaskQueue, TaskEnvelope


def _env(
    task_id: str, queue: str = "fast", priority: int = 0, at: float = 0.0, max_retries: int = 3
) -> TaskEnvelope:
    return TaskEnvelope(
        task_id=task_id,
        queue=queue,
        kind="warm_cache",
        priority=priority,
        enqueued_at=at,
        max_retries=max_retries,
    )


def test_bogus_queue_raises_value_error() -> None:
    with pytest.raises(ValueError):
        TaskEnvelope(
            task_id="t1",
            queue="bogus",
            kind="warm_cache",
            priority=0,
            enqueued_at=1.0,
        )


def test_negative_priority_raises_value_error() -> None:
    with pytest.raises(ValueError):
        _env("t1", priority=-1)


def test_dequeue_returns_higher_priority_first() -> None:
    q = FastTaskQueue()
    q.enqueue(_env("low", priority=1, at=1.0))
    q.enqueue(_env("high", priority=9, at=2.0))
    assert q.dequeue("fast").task_id == "high"


def test_equal_priority_dequeues_earliest_enqueued_at_first() -> None:
    q = FastTaskQueue()
    q.enqueue(_env("late", priority=5, at=100.0))
    q.enqueue(_env("early", priority=5, at=10.0))
    assert q.dequeue("fast").task_id == "early"


def test_dequeue_empty_returns_none() -> None:
    q = FastTaskQueue()
    assert q.dequeue("default") is None


def test_record_failure_dead_letters_after_max_retries() -> None:
    q = FastTaskQueue()
    q.enqueue(_env("t1", max_retries=2))
    # attempts 0 -> 1: still below max_retries (2) => retry.
    assert q.record_failure("t1") == "retry"
    # attempts 1 -> 2: reaches max_retries => dead_letter.
    assert q.record_failure("t1") == "dead_letter"
    dead = q.dead_letters()
    assert len(dead) == 1
    assert dead[0].task_id == "t1"
    assert dead[0].attempts == 2
    # No longer pending on its queue.
    assert q.pending("fast") == ()


def test_record_failure_returns_retry_and_increments_attempts() -> None:
    q = FastTaskQueue()
    q.enqueue(_env("t1", max_retries=3))
    assert q.record_failure("t1") == "retry"
    pending = q.pending("fast")
    assert len(pending) == 1
    assert pending[0].attempts == 1
    assert q.dead_letters() == ()


def test_pending_count_decrements_after_dequeue() -> None:
    q = FastTaskQueue()
    q.enqueue(_env("a", priority=1, at=1.0))
    q.enqueue(_env("b", priority=2, at=2.0))
    assert len(q.pending("fast")) == 2
    q.dequeue("fast")
    assert len(q.pending("fast")) == 1


def test_as_dict_queue_is_fast() -> None:
    env = _env("t1")
    assert env.as_dict()["queue"] == "fast"


def test_record_failure_unknown_task_raises_key_error() -> None:
    q = FastTaskQueue()
    with pytest.raises(KeyError):
        q.record_failure("nope")

"""Fast background task queue model — быстрая очередь фоновых задач (§9.10).

A pure, in-memory model of the *fast* background executor described in §9.10 —
the lightweight Redis/RQ-style worker that runs short-lived jobs (cache warms,
notifications, index touch-ups) **separately** from the heavyweight Dagster
ingestion pipeline. It captures the parts a scheduler must reason about without
touching Redis, RQ, or any network: named queues, priority ordering, FIFO
tie-breaking, and the retry / dead-letter decision.

* :class:`TaskEnvelope` — a frozen, JSON-serialisable unit of work. Its
  ``__post_init__`` rejects an unknown ``queue`` and a negative ``priority``.
* :class:`FastTaskQueue` — the in-memory broker. ``enqueue`` accepts an
  envelope; ``dequeue`` pops the **highest priority** task, breaking ties by
  earliest ``enqueued_at`` (FIFO — «первым пришёл, первым ушёл»);
  ``record_failure`` bumps ``attempts`` and returns ``'retry'`` until
  ``max_retries`` is exhausted, then ``'dead_letter'``.

Everything is side-effect free with respect to the outside world; the only
state is the queue's own in-memory buffers.

Public API:

* :data:`ALLOWED_QUEUES` — the frozen set of legal queue names.
* :class:`TaskEnvelope` — frozen task descriptor with :meth:`TaskEnvelope.as_dict`.
* :class:`FastTaskQueue` — the in-memory broker.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

# Named queues of the fast executor — именованные очереди (§9.10).
ALLOWED_QUEUES: frozenset[str] = frozenset({"default", "fast", "notifications"})

__all__ = [
    "ALLOWED_QUEUES",
    "FastTaskQueue",
    "TaskEnvelope",
]


@dataclass(frozen=True, slots=True)
class TaskEnvelope:
    """Immutable unit of fast work — неизменяемая единица работы (§9.10).

    ``priority`` is a non-negative integer where **larger means more urgent**;
    ``enqueued_at`` is a wall-clock timestamp used to break priority ties in
    FIFO order. ``attempts`` counts how many times the task has already failed.
    """

    task_id: str
    queue: str
    kind: str
    priority: int
    enqueued_at: float
    max_retries: int = 3
    attempts: int = 0

    def __post_init__(self) -> None:
        """Validate queue and priority — проверка очереди и приоритета (§9.10)."""
        if self.queue not in ALLOWED_QUEUES:
            allowed = ", ".join(sorted(ALLOWED_QUEUES))
            raise ValueError(f"unknown queue {self.queue!r}; allowed: {allowed}")
        if self.priority < 0:
            raise ValueError(f"priority must be >= 0, got {self.priority}")

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — конверт как словарь (§9.10)."""
        return {
            "task_id": self.task_id,
            "queue": self.queue,
            "kind": self.kind,
            "priority": self.priority,
            "enqueued_at": self.enqueued_at,
            "max_retries": self.max_retries,
            "attempts": self.attempts,
        }


@dataclass(slots=True)
class FastTaskQueue:
    """In-memory fast-task broker — брокер быстрых задач в памяти (§9.10).

    Holds one buffer per queue name plus a dead-letter buffer. All ordering is
    computed on ``dequeue`` so envelopes may be enqueued in any order.
    """

    _buffers: dict[str, list[TaskEnvelope]] = field(
        default_factory=lambda: {name: [] for name in ALLOWED_QUEUES}
    )
    _dead: list[TaskEnvelope] = field(default_factory=list)

    def enqueue(self, env: TaskEnvelope) -> None:
        """Append an envelope to its queue — поставить конверт в очередь (§9.10).

        The envelope has already validated its ``queue`` in ``__post_init__``,
        so the buffer is guaranteed to exist.
        """
        self._buffers[env.queue].append(env)

    def dequeue(self, queue: str) -> TaskEnvelope | None:
        """Pop the most urgent task — извлечь самую срочную задачу (§9.10).

        Highest ``priority`` wins; ties break by earliest ``enqueued_at``
        (FIFO). Returns ``None`` when the queue is empty.
        """
        buffer = self._buffers[queue]
        if not buffer:
            return None
        best_index = min(
            range(len(buffer)),
            key=lambda i: (-buffer[i].priority, buffer[i].enqueued_at),
        )
        return buffer.pop(best_index)

    def record_failure(self, task_id: str) -> str:
        """Register a failure — зарегистрировать сбой (§9.10).

        Searches the pending buffers for ``task_id``. If its ``attempts`` (after
        this failure) are still below ``max_retries`` the incremented envelope is
        re-queued and ``'retry'`` is returned; otherwise it is moved to the
        dead-letter buffer and ``'dead_letter'`` is returned.

        Raises ``KeyError`` when no pending task carries ``task_id``.
        """
        for buffer in self._buffers.values():
            for index, env in enumerate(buffer):
                if env.task_id == task_id:
                    return self._apply_failure(buffer, index, env)
        raise KeyError(f"no pending task with id {task_id!r}")

    def _apply_failure(self, buffer: list[TaskEnvelope], index: int, env: TaskEnvelope) -> str:
        """Bump attempts and route retry vs dead-letter — маршрутизация сбоя (§9.10)."""
        bumped = replace(env, attempts=env.attempts + 1)
        buffer.pop(index)
        if bumped.attempts >= bumped.max_retries:
            self._dead.append(bumped)
            return "dead_letter"
        buffer.append(bumped)
        return "retry"

    def pending(self, queue: str) -> tuple[TaskEnvelope, ...]:
        """Snapshot of a queue's pending tasks — ожидающие задачи очереди (§9.10)."""
        return tuple(self._buffers[queue])

    def dead_letters(self) -> tuple[TaskEnvelope, ...]:
        """Snapshot of dead-lettered tasks — «мёртвые» задачи (§9.10)."""
        return tuple(self._dead)

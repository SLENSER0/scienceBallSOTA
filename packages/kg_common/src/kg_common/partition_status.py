"""Partition materialization status board — статус материализации партиций (§9.6).

Companion to :mod:`kg_common.partitions` (§9.3): once a run is sliced into
partition keys, a scheduler needs to know *which* slices have been built. This
module tracks the materialization state of each partition key without taking a
dependency on any orchestrator — pure python, deterministic, side-effect free.

Each partition key carries one of four states («состояния»):

* ``pending``      — queued but not started («в очереди», the default);
* ``running``      — currently materializing («выполняется»);
* ``materialized`` — successfully built («материализована»);
* ``failed``       — the last attempt failed («ошибка»).

Everything here is deterministic:

* No wall-clock — :meth:`StatusBoard.set_status` takes an *explicit*
  ``updated_at`` timestamp instead of reading ``datetime.now`` (§9.6
  «детерминизм»), mirroring the explicit-start rule in :mod:`kg_common.partitions`.
* An unknown key reads back as ``pending`` with an empty timestamp, so callers
  never have to special-case «ключ ещё не встречался».

Public API:

* :data:`STATES`           — the four canonical states in canonical order.
* :class:`PartitionStatus` — frozen ``(key, state, updated_at)`` record with
  :meth:`PartitionStatus.as_dict`.
* :class:`StatusBoard`     — mutable board with :meth:`StatusBoard.set_status`,
  :meth:`StatusBoard.get_status` and :meth:`StatusBoard.summary`.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "DEFAULT_STATE",
    "STATES",
    "PartitionStatus",
    "StatusBoard",
]

#: Canonical states in canonical order — канонические состояния (§9.6).
STATES: tuple[str, ...] = ("pending", "running", "materialized", "failed")

#: State assumed for a key that was never set — состояние по умолчанию (§9.6).
DEFAULT_STATE = "pending"


@dataclass(frozen=True, slots=True)
class PartitionStatus:
    """Immutable status of one partition key — статус одной партиции (§9.6).

    ``key`` is the partition key (see :func:`kg_common.partitions.partition_key_for`);
    ``state`` is one of :data:`STATES`; ``updated_at`` is the *explicit* timestamp
    of the last transition (an empty string means «никогда не обновлялась»). The
    record is a plain frozen value so it can be hashed, compared and serialized.
    """

    key: str
    state: str
    updated_at: str

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — таблица «ключ + состояние + время» (§9.6)."""
        return {"key": self.key, "state": self.state, "updated_at": self.updated_at}


class StatusBoard:
    """Board of partition-key → :class:`PartitionStatus` — доска статусов (§9.6).

    Statuses are recorded with :meth:`set_status` (last write wins, so a key moves
    through the ``pending → running → materialized`` lifecycle by successive
    calls) and read back with :meth:`get_status`. An unknown key reads back as a
    :data:`DEFAULT_STATE` (``pending``) status with an empty timestamp rather than
    raising. :meth:`summary` aggregates the board into per-state counts and the
    percentage of tracked keys that are materialized.
    """

    def __init__(self) -> None:
        # Insertion-ordered registry of statuses keyed by partition key.
        self._statuses: dict[str, PartitionStatus] = {}

    def __contains__(self, key: object) -> bool:
        return key in self._statuses

    def __len__(self) -> int:
        return len(self._statuses)

    def set_status(self, key: str, state: str, updated_at: str) -> PartitionStatus:
        """Record ``state`` for ``key`` at explicit ``updated_at`` — задать статус (§9.6).

        Overwrites any previous status for ``key`` (last write wins), which is how
        a partition advances through its lifecycle. ``state`` must be one of
        :data:`STATES`; anything else is a programming error and raises
        :class:`ValueError`. Returns the stored :class:`PartitionStatus`.
        """
        if state not in STATES:
            raise ValueError(f"unknown state: {state!r} (expected one of {STATES})")
        status = PartitionStatus(key=key, state=state, updated_at=updated_at)
        self._statuses[key] = status
        return status

    def get_status(self, key: str) -> PartitionStatus:
        """Return the status of ``key`` — прочитать статус (§9.6).

        An unknown key yields a :data:`DEFAULT_STATE` (``pending``) status with an
        empty ``updated_at`` — «ключ ещё не встречался» — so callers never have to
        special-case a miss.
        """
        existing = self._statuses.get(key)
        if existing is not None:
            return existing
        return PartitionStatus(key=key, state=DEFAULT_STATE, updated_at="")

    def summary(self) -> dict[str, object]:
        """Aggregate the board — сводка по состояниям и % материализации (§9.6).

        Returns ``{"by_state": {state: count, ...}, "pct_materialized": float}``.
        ``by_state`` always lists **all** four :data:`STATES` (zero-filled) in
        canonical order, so the shape is stable. ``pct_materialized`` is the share
        of tracked keys in the ``materialized`` state, in ``0.0..100.0`` rounded to
        four decimals; an empty board reports ``0.0`` (no division by zero).
        """
        by_state: dict[str, int] = dict.fromkeys(STATES, 0)
        for status in self._statuses.values():
            by_state[status.state] += 1
        total = len(self._statuses)
        materialized = by_state["materialized"]
        pct = 0.0 if total == 0 else round(materialized / total * 100, 4)
        return {"by_state": by_state, "pct_materialized": pct}

"""Partitions backfill planning — планирование добора партиций (§9.3).

When a partitioned asset gains new partition keys (or an earlier run left some
keys *failed*), a scheduler needs a deterministic, order-preserving recipe for
*which* keys to re-materialise and *how* to chunk them into batches. This module
answers exactly that, without touching any store or scheduler.

* :func:`needs_backfill` — the per-key gate: a key needs work if it is **not
  completed**, or if it is **failed** (a failed key is re-run even when it also
  appears completed — «повторяем упавшие»).
* :func:`plan_backfill`  — apply the gate across an ordered key sequence,
  de-duplicate while preserving first-seen order, and chunk the survivors into
  fixed-size batches (``batch_size == 0`` => one batch with everything).
* :class:`BackfillPlan`  — the frozen, JSON-serialisable result.

Everything is a pure function of its inputs and side-effect free.

Public API:

* :class:`BackfillPlan` — frozen plan with :meth:`BackfillPlan.as_dict`.
* :func:`needs_backfill` — per-key predicate.
* :func:`plan_backfill`  — build a :class:`BackfillPlan`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

__all__ = [
    "BackfillPlan",
    "needs_backfill",
    "plan_backfill",
]


@dataclass(frozen=True, slots=True)
class BackfillPlan:
    """Immutable backfill recipe — неизменяемый план добора (§9.3).

    ``pending`` is the ordered, de-duplicated list of partition keys to
    re-materialise; ``batches`` is the same list chunked for execution. When
    ``pending`` is empty, ``batches`` is empty too — there is nothing to run.
    """

    name: str
    pending: tuple[str, ...]
    batches: tuple[tuple[str, ...], ...]

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — план как словарь (§9.3)."""
        return {
            "name": self.name,
            "pending": list(self.pending),
            "batches": [list(batch) for batch in self.batches],
        }


def needs_backfill(key: str, completed: set[str], failed: set[str]) -> bool:
    """Does ``key`` need a (re)run? — нужно ли добирать ключ? (§9.3).

    ``True`` iff the key is **not** in ``completed`` OR it is in ``failed``.
    A failed key is always re-run, even if it is also marked completed.
    """
    return key not in completed or key in failed


def plan_backfill(
    partition_keys: Iterable[str],
    completed: set[str],
    failed: set[str] = frozenset(),
    *,
    batch_size: int = 0,
    name: str = "backfill",
) -> BackfillPlan:
    """Plan a partitions backfill — построить план добора партиций (§9.3).

    Walks ``partition_keys`` in order, keeping every key for which
    :func:`needs_backfill` is ``True``, de-duplicating on first-seen order.
    The survivors are chunked into batches of ``batch_size`` (``0`` => a single
    batch holding everything). An empty ``pending`` yields empty ``batches``.
    """
    seen: set[str] = set()
    pending: list[str] = []
    for key in partition_keys:
        if key in seen:
            continue
        seen.add(key)
        if needs_backfill(key, completed, failed):
            pending.append(key)

    if not pending:
        batches: tuple[tuple[str, ...], ...] = ()
    elif batch_size <= 0:
        batches = (tuple(pending),)
    else:
        batches = tuple(
            tuple(pending[i : i + batch_size]) for i in range(0, len(pending), batch_size)
        )

    return BackfillPlan(name=name, pending=tuple(pending), batches=batches)

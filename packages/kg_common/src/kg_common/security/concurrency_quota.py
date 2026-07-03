"""Per-user concurrency quota accounting (§19.4 rate limiting / abuse).

In-memory, Redis-semaphore-style admission control
(«учёт квоты одновременных запросов на пользователя»). A request tries to
acquire a slot before running and releases it when finished. Admission is
denied when the user already holds ``per_user_max`` slots, or when the shared
pool already holds ``global_max`` slots (fairness + overload protection).

This mirrors the semantics of a Redis semaphore (INCR/DECR with ceilings) but
keeps all state in process memory, so it is exact and hand-checkable in tests.
Not thread-safe by itself — wrap in a lock if shared across threads.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class ConcurrencyQuota:
    """Immutable ceilings for concurrent requests (§19.4).

    :param per_user_max: макс. одновременных запросов на одного пользователя.
    :param global_max: макс. одновременных запросов во всём пуле.
    """

    per_user_max: int
    global_max: int

    def __post_init__(self) -> None:
        if self.per_user_max < 0:
            raise ValueError("per_user_max must be non-negative")
        if self.global_max < 0:
            raise ValueError("global_max must be non-negative")

    def as_dict(self) -> dict[str, int]:
        """Serialize the quota to a plain dict (для конфигов/телеметрии)."""
        return {"per_user_max": self.per_user_max, "global_max": self.global_max}


class ConcurrencyTracker:
    """Mutable slot accountant for a :class:`ConcurrencyQuota` (§19.4).

    Tracks per-user in-flight counts and a running global total. ``try_acquire``
    is all-or-nothing: it only mutates state when admission succeeds
    («либо занимаем слот, либо ничего не меняем»).
    """

    def __init__(self, quota: ConcurrencyQuota) -> None:
        self._quota = quota
        self._per_user: dict[str, int] = defaultdict(int)
        self._global: int = 0

    @property
    def quota(self) -> ConcurrencyQuota:
        """The immutable quota backing this tracker."""
        return self._quota

    def try_acquire(self, user_id: str) -> bool:
        """Try to take one slot for ``user_id``; return whether it succeeded.

        Fails (без изменения состояния) when the user is at ``per_user_max`` or
        the global pool is at ``global_max``.
        """
        if self._per_user[user_id] >= self._quota.per_user_max:
            return False
        if self._global >= self._quota.global_max:
            return False
        self._per_user[user_id] += 1
        self._global += 1
        return True

    def release(self, user_id: str) -> None:
        """Release one slot for ``user_id``; never drops below zero.

        Releasing a user with no held slots is a no-op («освобождение
        несуществующего слота ничего не делает»).
        """
        current = self._per_user.get(user_id, 0)
        if current <= 0:
            return
        if current == 1:
            del self._per_user[user_id]
        else:
            self._per_user[user_id] = current - 1
        if self._global > 0:
            self._global -= 1

    def in_use(self, user_id: str) -> int:
        """Slots currently held by ``user_id`` (0 if none)."""
        return self._per_user.get(user_id, 0)

    def global_in_use(self) -> int:
        """Total slots currently held across all users."""
        return self._global

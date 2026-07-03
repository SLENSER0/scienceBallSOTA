"""§13.20 долговременная память Store (между сессиями) / long-term Store memory.

Unlike :mod:`conversation_memory` (a per-session token buffer), this models the
LangGraph ``PostgresStore`` long-term memory that survives across sessions and is
namespaced **per user** (§13.20). Each :class:`MemoryRecord` is a frozen, JSON-
serialisable fact the agent has learned about a user — a canonical entity, an alias,
a stated preference, or a frequently used filter — carrying a ``created_at`` timestamp
and an optional ``ttl_s`` time-to-live (срок жизни / time-to-live).

Two pure helpers operate on records without any store or network:

* :func:`namespace` — the ``(user_id, "memories")`` tuple the Store keys records under.
* :func:`prune` — drop expired records, then keep only the newest ``max_items`` by
  ``created_at`` (усечение по свежести / recency truncation).

Everything here is deterministic and hand-checkable, so the module is unit-testable in
isolation from the real ``PostgresStore``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Kinds a memory record may carry (виды записей / record kinds). Others raise.
KINDS: frozenset[str] = frozenset({"canonical_entity", "alias", "preference", "frequent_filter"})


@dataclass(frozen=True)
class MemoryRecord:
    """One long-term memory fact about a user (§13.20): a namespaced key/value.

    Frozen and JSON-serialisable via :meth:`as_dict`. ``kind`` must be one of
    :data:`KINDS` (иначе ошибка / else raises). ``ttl_s`` is an optional lifetime in
    seconds measured from ``created_at``; ``None`` means the record never expires.
    """

    key: str
    kind: str
    value: dict[str, Any]
    created_at: float
    ttl_s: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown kind {self.kind!r} / неизвестный вид записи")

    def is_expired(self, now: float) -> bool:
        """Whether this record has expired by ``now`` (истёк ли срок / has TTL lapsed).

        ``ttl_s is None`` → never expires (``False``). Otherwise expired once
        ``now >= created_at + ttl_s`` (напр. created_at=0, ttl_s=10, now=100 → ``True``).
        """
        if self.ttl_s is None:
            return False
        return now >= self.created_at + self.ttl_s

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{key, kind, value, created_at, ttl_s}`` (stable order)."""
        return {
            "key": self.key,
            "kind": self.kind,
            "value": dict(self.value),
            "created_at": self.created_at,
            "ttl_s": self.ttl_s,
        }


def namespace(user_id: str) -> tuple[str, str]:
    """The Store namespace tuple ``(user_id, "memories")`` for a user (§13.20).

    Records for a user are keyed under this namespace so different users never collide
    (изоляция по пользователю / per-user isolation).
    """
    return (user_id, "memories")


def prune(records: list[MemoryRecord], now: float, max_items: int) -> list[MemoryRecord]:
    """Drop expired records, then keep the newest ``max_items`` by ``created_at``.

    First every record with :meth:`MemoryRecord.is_expired` at ``now`` is removed; the
    survivors are then sorted newest→oldest and truncated to ``max_items`` (усечение по
    свежести / recency truncation). ``max_items <= 0`` → ``[]``. Fewer survivors than
    ``max_items`` → all survivors, newest→oldest.
    """
    if max_items <= 0:
        return []
    fresh = [r for r in records if not r.is_expired(now)]
    fresh.sort(key=lambda r: r.created_at, reverse=True)
    return fresh[:max_items]

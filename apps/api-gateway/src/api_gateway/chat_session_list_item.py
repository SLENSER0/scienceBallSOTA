"""Chat session list item DTO, sorter and date filter (§14.4).

Элемент списка сессий чата для ``GET /chat/sessions``: неизменяемый frozen
dataclass ``SessionListItem`` с полями ``session_id``, ``title``,
``created_at`` и ``last_message_at`` (последнее по умолчанию равно
``created_at``, когда в строке ``NULL``). Есть :meth:`as_dict` и фабрика
:meth:`from_row`, а также сортировка по ``last_message_at`` и фильтр по датам
через сравнение ISO-8601 строк.

A session list item for ``GET /chat/sessions``: an immutable frozen dataclass
``SessionListItem`` (``session_id``, ``title``, ``created_at``,
``last_message_at``) where a null ``last_message_at`` defaults to
``created_at``. Pure stdlib; ISO-8601 strings sort/compare lexically.

* :class:`SessionListItem` — frozen row record with :meth:`as_dict`/:meth:`from_row`.
* :func:`sort_sessions` — order items by ``last_message_at`` (newest first by default).
* :func:`filter_by_date` — keep items whose ``last_message_at`` is in ``[since, until]``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SessionListItem:
    """Неизменяемый элемент списка сессий чата (§14.4).

    Immutable chat session list item. ``last_message_at`` may be ``None`` at the
    type level but :meth:`from_row` fills it from ``created_at`` when the row is
    null, so filtering/sorting always have a comparable timestamp.
    """

    session_id: str
    title: str
    created_at: str
    last_message_at: str | None

    def as_dict(self) -> dict[str, Any]:
        """Сериализовать в JSON-совместимый dict с четырьмя ключами.

        Serialise to a JSON-ready ``dict`` with exactly the four fields.
        """
        return {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at,
            "last_message_at": self.last_message_at,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> SessionListItem:
        """Построить из строки; ``last_message_at=None`` → ``created_at`` (§14.4).

        Build from a mapping row. A null/missing ``last_message_at`` defaults to
        ``created_at`` so downstream sort/filter never see ``None``.
        """
        created_at = str(row["created_at"])
        last = row.get("last_message_at")
        last_message_at = created_at if last is None else str(last)
        return cls(
            session_id=str(row["session_id"]),
            title=str(row["title"]),
            created_at=created_at,
            last_message_at=last_message_at,
        )


def _sort_key(item: SessionListItem) -> str:
    """Ключ сортировки по ``last_message_at`` (fallback — ``created_at``).

    Sort key: ``last_message_at`` if present, else ``created_at``.
    """
    return item.last_message_at if item.last_message_at is not None else item.created_at


def sort_sessions(items: Sequence[SessionListItem], *, desc: bool = True) -> list[SessionListItem]:
    """Отсортировать сессии по ``last_message_at`` (§14.4).

    Order items by ``last_message_at`` using ISO-8601 string comparison; newest
    first when ``desc`` is true (the default), oldest first otherwise.
    """
    return sorted(items, key=_sort_key, reverse=desc)


def filter_by_date(
    items: Sequence[SessionListItem],
    *,
    since: str | None = None,
    until: str | None = None,
) -> list[SessionListItem]:
    """Отфильтровать сессии по диапазону дат ``[since, until]`` (§14.4).

    Keep items whose ``last_message_at`` is ``>= since`` and ``<= until`` using
    ISO-8601 string comparison; a ``None`` bound is treated as open-ended.
    """
    result: list[SessionListItem] = []
    for item in items:
        stamp = _sort_key(item)
        if since is not None and stamp < since:
            continue
        if until is not None and stamp > until:
            continue
        result.append(item)
    return result

"""Tests for the chat session list item DTO/sorter/filter (§14.4).

Проверяем frozen dataclass, дефолт ``last_message_at``, сериализацию,
сортировку по обоим направлениям и фильтр по ISO-8601 датам.
"""

from __future__ import annotations

import dataclasses

import pytest
from api_gateway.chat_session_list_item import (
    SessionListItem,
    filter_by_date,
    sort_sessions,
)


def _item(
    session_id: str,
    last: str | None,
    created: str = "2025-06-01T00:00:00Z",
) -> SessionListItem:
    """Собрать элемент через :meth:`from_row` для краткости тестов."""
    return SessionListItem.from_row(
        {
            "session_id": session_id,
            "title": f"title-{session_id}",
            "created_at": created,
            "last_message_at": last,
        }
    )


def test_from_row_null_last_message_defaults_to_created() -> None:
    """(1) from_row с last_message_at=None → last_message_at == created_at."""
    item = SessionListItem.from_row(
        {
            "session_id": "s1",
            "title": "Hello",
            "created_at": "2026-03-01T10:00:00Z",
            "last_message_at": None,
        }
    )
    assert item.last_message_at == "2026-03-01T10:00:00Z"
    assert item.last_message_at == item.created_at


def test_from_row_missing_last_message_defaults_to_created() -> None:
    """from_row без ключа last_message_at тоже берёт created_at."""
    item = SessionListItem.from_row(
        {
            "session_id": "s1",
            "title": "Hello",
            "created_at": "2026-03-01T10:00:00Z",
        }
    )
    assert item.last_message_at == "2026-03-01T10:00:00Z"


def test_as_dict_has_four_keys() -> None:
    """(2) as_dict() содержит ровно четыре ключа."""
    item = _item("s1", "2026-05-01T00:00:00Z")
    d = item.as_dict()
    assert set(d) == {"session_id", "title", "created_at", "last_message_at"}
    assert d["session_id"] == "s1"
    assert d["last_message_at"] == "2026-05-01T00:00:00Z"


def test_sort_desc_newest_first() -> None:
    """(3) sort_sessions desc=True ставит самый новый last_message_at первым."""
    items = [
        _item("old", "2026-01-01T00:00:00Z"),
        _item("new", "2026-06-01T00:00:00Z"),
        _item("mid", "2026-03-01T00:00:00Z"),
    ]
    order = [i.session_id for i in sort_sessions(items, desc=True)]
    assert order == ["new", "mid", "old"]


def test_sort_asc_reverses() -> None:
    """(4) desc=False переворачивает порядок (самый старый первым)."""
    items = [
        _item("old", "2026-01-01T00:00:00Z"),
        _item("new", "2026-06-01T00:00:00Z"),
        _item("mid", "2026-03-01T00:00:00Z"),
    ]
    order = [i.session_id for i in sort_sessions(items, desc=False)]
    assert order == ["old", "mid", "new"]


def test_filter_since_drops_earlier() -> None:
    """(5) filter_by_date since='2026-01-01' отбрасывает более ранние."""
    items = [
        _item("y2025", "2025-12-31T00:00:00Z"),
        _item("y2026", "2026-02-01T00:00:00Z"),
    ]
    kept = [i.session_id for i in filter_by_date(items, since="2026-01-01")]
    assert kept == ["y2026"]


def test_filter_until_drops_later() -> None:
    """(6) until='2026-06-01' отбрасывает более поздние."""
    items = [
        _item("early", "2026-02-01T00:00:00Z"),
        _item("late", "2026-09-01T00:00:00Z"),
    ]
    kept = [i.session_id for i in filter_by_date(items, until="2026-06-01")]
    assert kept == ["early"]


def test_filter_since_and_until_keeps_in_range() -> None:
    """(7) since+until оставляет только запись внутри диапазона."""
    items = [
        _item("before", "2025-12-01T00:00:00Z"),
        _item("inrange", "2026-03-15T00:00:00Z"),
        _item("after", "2026-09-01T00:00:00Z"),
    ]
    kept = [i.session_id for i in filter_by_date(items, since="2026-01-01", until="2026-06-01")]
    assert kept == ["inrange"]


def test_session_list_item_is_frozen() -> None:
    """(8) SessionListItem неизменяем (frozen)."""
    item = _item("s1", "2026-05-01T00:00:00Z")
    assert dataclasses.is_dataclass(item)
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.title = "changed"  # type: ignore[misc]

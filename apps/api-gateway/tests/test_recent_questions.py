"""Tests for the Home recent-questions block model (§17.6).

Проверяем дедуп по нормализованному тексту, сохранение самой свежей записи,
сортировку по убыванию ``asked_at``, обрезку по ``limit`` при полном ``total``,
логику превью и camelCase-сериализацию.
"""

from __future__ import annotations

import dataclasses

import pytest
from api_gateway.recent_questions import (
    RecentQuestion,
    RecentQuestionList,
    build_recent_questions,
)


def _row(session_id: str, text: str, asked_at: str) -> dict:
    """Собрать сырую строку вопроса для краткости тестов."""
    return {"session_id": session_id, "text": text, "asked_at": asked_at}


def test_duplicate_collapses_keeping_later_asked_at() -> None:
    """(1) Два одинаковых текста → одна запись с более поздним asked_at."""
    raw = [
        _row("s-old", "What is Al Cu?", "2026-01-01T00:00:00Z"),
        _row("s-new", "What is Al Cu?", "2026-06-01T00:00:00Z"),
    ]
    result = build_recent_questions(raw)
    assert len(result.items) == 1
    kept = result.items[0]
    assert kept.asked_at == "2026-06-01T00:00:00Z"
    assert kept.session_id == "s-new"


def test_sorted_newest_first() -> None:
    """(2) items отсортированы по убыванию asked_at (новейший первым)."""
    raw = [
        _row("a", "alpha", "2026-01-01T00:00:00Z"),
        _row("b", "beta", "2026-06-01T00:00:00Z"),
        _row("c", "gamma", "2026-03-01T00:00:00Z"),
    ]
    result = build_recent_questions(raw)
    order = [i.text for i in result.items]
    assert order == ["beta", "gamma", "alpha"]
    assert result.items[0].asked_at == "2026-06-01T00:00:00Z"


def test_total_counts_distinct_dup_case() -> None:
    """(3) total считает уникальные вопросы (==1 для дубликата)."""
    raw = [
        _row("s1", "Same question?", "2026-01-01T00:00:00Z"),
        _row("s2", "Same question?", "2026-02-01T00:00:00Z"),
        _row("s3", "Same question?", "2026-03-01T00:00:00Z"),
    ]
    result = build_recent_questions(raw)
    assert result.total == 1
    assert len(result.items) == 1


def test_limit_truncates_items_but_total_reflects_all() -> None:
    """(4) limit=1 → ровно 1 item, но total отражает все уникальные."""
    raw = [
        _row("a", "q one", "2026-01-01T00:00:00Z"),
        _row("b", "q two", "2026-02-01T00:00:00Z"),
        _row("c", "q three", "2026-03-01T00:00:00Z"),
    ]
    result = build_recent_questions(raw, limit=1)
    assert len(result.items) == 1
    assert result.total == 3
    # самый свежий остаётся при обрезке
    assert result.items[0].text == "q three"


def test_preview_of_long_text_length_and_ellipsis() -> None:
    """(5) Превью 100-символьного текста имеет длину 83 и оканчивается '...'."""
    text = "x" * 100
    raw = [_row("s1", text, "2026-01-01T00:00:00Z")]
    result = build_recent_questions(raw)
    preview = result.items[0].preview
    assert len(preview) == 83
    assert preview.endswith("...")
    assert preview[:80] == "x" * 80


def test_preview_of_short_text_unchanged() -> None:
    """(6) Превью 10-символьного текста равно самому тексту без изменений."""
    text = "0123456789"  # ровно 10 символов
    raw = [_row("s1", text, "2026-01-01T00:00:00Z")]
    result = build_recent_questions(raw)
    assert result.items[0].preview == text


def test_dedupe_is_case_and_space_insensitive() -> None:
    """(7) 'Al Cu?' и 'al cu? ' считаются одним вопросом."""
    raw = [
        _row("s1", "Al Cu?", "2026-01-01T00:00:00Z"),
        _row("s2", "al cu? ", "2026-05-01T00:00:00Z"),
    ]
    result = build_recent_questions(raw)
    assert result.total == 1
    assert len(result.items) == 1
    # сохраняется самая свежая запись (её оригинальный текст)
    assert result.items[0].asked_at == "2026-05-01T00:00:00Z"
    assert result.items[0].text == "al cu? "


def test_as_dict_camel_case_keys() -> None:
    """(8) as_dict() выдаёт camelCase-ключи 'sessionId'/'askedAt'."""
    q = RecentQuestion(
        session_id="s1",
        text="hello",
        asked_at="2026-01-01T00:00:00Z",
        preview="hello",
    )
    d = q.as_dict()
    assert set(d) == {"sessionId", "text", "askedAt", "preview"}
    assert d["sessionId"] == "s1"
    assert d["askedAt"] == "2026-01-01T00:00:00Z"


def test_list_as_dict_serialises_items() -> None:
    """(9) RecentQuestionList.as_dict() сериализует items и total."""
    result = build_recent_questions([_row("s1", "q", "2026-01-01T00:00:00Z")])
    d = result.as_dict()
    assert d["total"] == 1
    assert isinstance(d["items"], list)
    assert d["items"][0]["sessionId"] == "s1"


def test_records_are_frozen() -> None:
    """(10) RecentQuestion и RecentQuestionList неизменяемы (frozen)."""
    q = RecentQuestion(session_id="s1", text="t", asked_at="a", preview="t")
    assert dataclasses.is_dataclass(q)
    with pytest.raises(dataclasses.FrozenInstanceError):
        q.text = "changed"  # type: ignore[misc]
    lst = RecentQuestionList(items=(q,), total=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        lst.total = 99  # type: ignore[misc]


def test_empty_raw_yields_empty_list() -> None:
    """(11) Пустой вход → пустой список и total==0."""
    result = build_recent_questions([])
    assert result.items == ()
    assert result.total == 0

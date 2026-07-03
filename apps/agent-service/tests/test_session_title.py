"""§13.24 тесты деривации заголовка чат-сессии / session-title derivation tests.

Проверяет сворачивание пробелов, срез завершающей пунктуации, обрезку по границе
слова с ``…``, fallback на ``'New chat'`` и orjson-сериализуемость ``as_dict``.
"""

from __future__ import annotations

import orjson
from agent_service.session_title import SessionTitle, derive_title


def test_trailing_question_mark_stripped_not_truncated() -> None:
    # (1) завершающий '?' срезается, обрезки нет / trailing '?' stripped, no cut.
    result = derive_title("What is Al-Cu hardness?")
    assert result.title == "What is Al-Cu hardness"
    assert result.truncated is False


def test_long_question_cut_on_word_boundary() -> None:
    # (2) >60 символов режется по границе слова, оканчивается '…', в пределах max_len+1.
    question = "What is the exact Vickers hardness value of an aged aluminium copper alloy sample"
    assert len(question) > 60
    result = derive_title(question, max_len=60)
    assert result.truncated is True
    assert result.title.endswith("…")
    assert len(result.title) <= 60 + 1
    # Граница слова: тело заголовка (без '…') не обрывает слово посреди / word boundary.
    body = result.title[:-1]
    assert not question[len(body) : len(body) + 1].strip() or question.startswith(body)
    assert " " in result.title  # обрезали по пробелу, слова целые / whole words kept


def test_whitespace_collapsed() -> None:
    # (3) внутренние пробелы сворачиваются / internal whitespace collapsed.
    result = derive_title("a\n\n  b")
    assert result.title == "a b"
    assert result.truncated is False


def test_empty_string_falls_back() -> None:
    # (4) пустая строка -> 'New chat' / empty string fallback.
    result = derive_title("")
    assert result.title == "New chat"
    assert result.truncated is False


def test_whitespace_only_falls_back() -> None:
    # (5) только пробелы -> 'New chat' / whitespace-only fallback.
    result = derive_title("   \n\t  ")
    assert result.title == "New chat"
    assert result.truncated is False


def test_turn_count_echoed() -> None:
    # (6) turn_count переносится в датакласс и as_dict / echoed through.
    result = derive_title("Question here", turn_count=7)
    assert result.turn_count == 7
    assert result.as_dict()["turn_count"] == 7


def test_turn_count_echoed_on_fallback() -> None:
    # (6b) эхо turn_count работает и на fallback-ветке / echo also on fallback.
    result = derive_title("", turn_count=4)
    assert result.turn_count == 4
    assert result.as_dict()["turn_count"] == 4


def test_short_question_never_truncated() -> None:
    # (7) короче max_len — никогда не режется / short question never truncated.
    question = "Short one"
    assert len(question) < 60
    result = derive_title(question, max_len=60)
    assert result.title == "Short one"
    assert result.truncated is False


def test_as_dict_is_orjson_serialisable() -> None:
    # (8) as_dict сериализуется orjson / orjson round-trips as_dict.
    result = derive_title("What is Al-Cu hardness?", turn_count=3)
    raw = orjson.dumps(result.as_dict())
    loaded = orjson.loads(raw)
    assert loaded == {
        "title": "What is Al-Cu hardness",
        "truncated": False,
        "turn_count": 3,
    }


def test_dataclass_frozen() -> None:
    # SessionTitle заморожен / SessionTitle is immutable.
    result = SessionTitle(title="x", truncated=False, turn_count=1)
    try:
        result.title = "y"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("SessionTitle must be frozen")


def test_single_long_word_truncated_within_bound() -> None:
    # Одно слово длиннее предела всё равно обрезается в границах / single long word.
    question = "x" * 80
    result = derive_title(question, max_len=60)
    assert result.truncated is True
    assert result.title.endswith("…")
    assert len(result.title) <= 60 + 1

"""§13.24 tests for internal HTTP API request contracts / тесты контрактов запросов API."""

from __future__ import annotations

from agent_service.api_contracts import (
    CreateSessionRequest,
    MessageRequest,
    ResumeRequest,
    validate_message,
    validate_resume,
)


def test_empty_question_errors() -> None:
    """(1) Empty question yields an error mentioning 'question' / пустой вопрос — ошибка."""
    errors = validate_message(MessageRequest(session_id="s1", question=""))
    assert errors
    assert any("question" in e for e in errors)


def test_whitespace_question_errors() -> None:
    """(2) Whitespace-only question also errors / вопрос из пробелов — тоже ошибка."""
    errors = validate_message(MessageRequest(session_id="s1", question="   "))
    assert any("question" in e for e in errors)


def test_valid_message_no_errors() -> None:
    """(3) A valid message request returns [] / корректный запрос — пустой список."""
    req = MessageRequest(session_id="s1", question="What is bainite?", language="en")
    assert validate_message(req) == []


def test_language_validation() -> None:
    """(4) language='fr' errors, language=None does not / 'fr' — ошибка, None — нет."""
    bad = validate_message(MessageRequest(session_id="s1", question="q", language="fr"))
    assert any("language" in e for e in bad)
    ok = validate_message(MessageRequest(session_id="s1", question="q", language=None))
    assert all("language" not in e for e in ok)
    assert ok == []


def test_resume_blank_session_errors() -> None:
    """(5) validate_resume with blank session_id errors / пустой session_id — ошибка."""
    errors = validate_resume(ResumeRequest(session_id="", resume_value="Al-Cu"))
    assert any("session_id" in e for e in errors)


def test_create_session_as_dict_includes_none_session_id() -> None:
    """(6) as_dict keeps session_id even when None / session_id есть даже при None."""
    d = CreateSessionRequest(user_id="u1").as_dict()
    assert "session_id" in d
    assert d["session_id"] is None
    assert d["user_id"] == "u1"


def test_message_as_dict_round_trips_all_fields() -> None:
    """(7) MessageRequest.as_dict round-trips all three fields / все три поля сохранены."""
    req = MessageRequest(session_id="s1", question="q", language="ru")
    d = req.as_dict()
    assert d == {"session_id": "s1", "question": "q", "language": "ru"}


def test_resume_empty_value_errors() -> None:
    """Empty resume_value is flagged / пустое значение возобновления — ошибка."""
    errors = validate_resume(ResumeRequest(session_id="s1", resume_value="  "))
    assert any("resume_value" in e for e in errors)


def test_valid_resume_no_errors() -> None:
    """A valid resume request returns [] / корректный запрос возобновления — пустой список."""
    assert validate_resume(ResumeRequest(session_id="s1", resume_value="Al-Cu")) == []

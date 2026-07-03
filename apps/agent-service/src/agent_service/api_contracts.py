"""§13.24 internal HTTP API request contracts / контракты запросов внутреннего HTTP API.

The agent-service exposes internal endpoints consumed by the api-gateway: create a
session, post a message, resume an interrupted run, and read a trace. This module holds
the request DTOs and their validation, kept pure-python so they stay unit-testable without
a seeded Kuzu store (свойства узлов Kuzu не являются колонками запроса / node props are not
queryable columns — irrelevant here, no store access).

Surface:

* :class:`CreateSessionRequest` — frozen ``(user_id, session_id=None)`` with :meth:`as_dict`.
* :class:`MessageRequest` — frozen ``(session_id, question, language=None)`` with :meth:`as_dict`.
* :class:`ResumeRequest` — frozen ``(session_id, resume_value)`` with :meth:`as_dict`.
* :func:`validate_message` — human-readable errors for a :class:`MessageRequest`.
* :func:`validate_resume` — human-readable errors for a :class:`ResumeRequest`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Accepted answer languages (допустимые языки ответа / accepted answer languages).
ALLOWED_LANGUAGES: frozenset[str] = frozenset({"ru", "en"})


@dataclass(frozen=True)
class CreateSessionRequest:
    """Create-session request / запрос на создание сессии.

    ``session_id`` is optional — the service mints one when it is ``None``
    (сервис создаёт идентификатор, если он не задан / minted when omitted).
    """

    user_id: str
    session_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe projection / JSON-совместимая проекция.

        ``session_id`` is always present, even when ``None``.
        """
        return {"user_id": self.user_id, "session_id": self.session_id}


@dataclass(frozen=True)
class MessageRequest:
    """Post-message request / запрос на отправку сообщения.

    ``language`` may be ``'ru'``, ``'en'`` or ``None`` (auto-detect / автоопределение).
    """

    session_id: str
    question: str
    language: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe projection / JSON-совместимая проекция (all three fields)."""
        return {
            "session_id": self.session_id,
            "question": self.question,
            "language": self.language,
        }


@dataclass(frozen=True)
class ResumeRequest:
    """Resume-interrupt request / запрос на возобновление после прерывания."""

    session_id: str
    resume_value: str

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe projection / JSON-совместимая проекция."""
        return {"session_id": self.session_id, "resume_value": self.resume_value}


def validate_message(req: MessageRequest) -> list[str]:
    """Return human-readable errors for ``req`` / вернуть читаемые ошибки.

    Empty list means the request is valid (пустой список — запрос корректен / valid).
    """
    errors: list[str] = []
    if not req.question.strip():
        errors.append("question is empty")
    if not req.session_id.strip():
        errors.append("session_id is blank")
    if req.language is not None and req.language not in ALLOWED_LANGUAGES:
        errors.append("language must be 'ru'/'en'/None")
    return errors


def validate_resume(req: ResumeRequest) -> list[str]:
    """Return human-readable errors for ``req`` / вернуть читаемые ошибки.

    Empty list means the request is valid (пустой список — запрос корректен / valid).
    """
    errors: list[str] = []
    if not req.session_id.strip():
        errors.append("session_id is blank")
    if not req.resume_value.strip():
        errors.append("resume_value is empty")
    return errors

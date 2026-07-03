"""§13.24 in-memory модель chat_sessions/chat_messages / chat-session store.

§13.24 описывает HTTP API сервиса агента и персистентные таблицы
``chat_sessions``/``chat_messages``, но нет чистой доменной модели этих строк,
пригодной для юнит-тестов и для сборки полезной нагрузки до записи в БД. Этот
модуль закрывает пробел: неизменяемые датаклассы :class:`ChatMessage` и
:class:`ChatSession` плюс чистые функции для создания сессии, добавления
сообщения (иммутабельно — возвращается новый объект), поиска последнего
пользовательского сообщения и подсчёта сообщений.

Логика чистая и детерминированная (нет графа, нет БД, нет LLM): время подаётся
вызывающим как ``now: float``, поэтому всё тривиально хэнд-чекается. §13.24
chat_sessions/chat_messages tables modelled as frozen dataclasses with an
immutable append; :meth:`as_dict` renders orjson-safe plain dicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Допустимые роли сообщения / allowed message roles per §13.24.
_ALLOWED_ROLES: frozenset[str] = frozenset({"user", "assistant", "system"})


@dataclass(frozen=True)
class ChatMessage:
    """Одно сообщение чат-сессии / a single chat message row (§13.24).

    ``message_id`` — идентификатор строки; ``role`` — одна из
    ``{'user','assistant','system'}``; ``content`` — текст; ``created_at`` —
    epoch-секунды создания. Датакласс неизменяем и JSON-готов.
    """

    message_id: str
    role: str
    content: str
    created_at: float

    def as_dict(self) -> dict[str, Any]:
        """orjson-безопасный dict / an orjson-serialisable plain dict."""
        return {
            "message_id": self.message_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ChatSession:
    """Строка chat-сессии со своими сообщениями / a chat session with messages.

    ``session_id`` — идентификатор сессии; ``user_id`` — владелец; ``created_at``
    — epoch-секунды создания; ``messages`` — кортеж :class:`ChatMessage` в порядке
    вставки. Датакласс неизменяем; :meth:`as_dict` проецирует сообщения в список
    dict-ов.
    """

    session_id: str
    user_id: str
    created_at: float
    messages: tuple[ChatMessage, ...] = field(default=())

    def as_dict(self) -> dict[str, Any]:
        """orjson-безопасный dict / an orjson-serialisable plain dict."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "messages": [msg.as_dict() for msg in self.messages],
        }


def new_session(session_id: str, user_id: str, now: float) -> ChatSession:
    """Создать пустую чат-сессию / create an empty chat session (§13.24).

    Возвращает :class:`ChatSession` без сообщений; ``created_at`` берётся из
    поданного ``now`` (epoch-секунды).
    """
    return ChatSession(session_id=session_id, user_id=user_id, created_at=now)


def append_message(
    session: ChatSession,
    role: str,
    content: str,
    message_id: str,
    now: float,
) -> ChatSession:
    """Добавить сообщение иммутабельно / append a message immutably.

    Возвращает НОВЫЙ :class:`ChatSession` с добавленным в конец сообщением;
    исходная сессия не изменяется. ``role`` должен входить в
    ``{'user','assistant','system'}``, иначе :class:`ValueError`.
    """
    if role not in _ALLOWED_ROLES:
        allowed = ", ".join(sorted(_ALLOWED_ROLES))
        raise ValueError(f"role must be one of {{{allowed}}}, got {role!r}")
    message = ChatMessage(
        message_id=message_id,
        role=role,
        content=content,
        created_at=now,
    )
    return ChatSession(
        session_id=session.session_id,
        user_id=session.user_id,
        created_at=session.created_at,
        messages=(*session.messages, message),
    )


def last_user_message(session: ChatSession) -> ChatMessage | None:
    """Последнее сообщение с ``role=='user'`` / the most recent user message.

    Возвращает самое позднее по порядку вставки сообщение пользователя или
    ``None``, если таких сообщений нет.
    """
    for message in reversed(session.messages):
        if message.role == "user":
            return message
    return None


def message_count(session: ChatSession) -> int:
    """Число сообщений в сессии / count of messages in the session."""
    return len(session.messages)

"""Chat SSE / ``ChatStreamEvent`` serialization (§14.4 / §5.3).

Валидация и SSE-обрамление контракта §5.3 ``ChatStreamEvent`` на чистом stdlib.
Сегодня в ``routers/chat.py`` и ``routers/query.py`` живёт лишь приватная
``_sse()`` без проверки типа события — этот модуль централизует контракт:
замороженный класс события, множество допустимых типов, рендер SSE-фрейма
(``event:`` + ``data:``, опциональный ``id:``), heartbeat-комментарий и разбор
заголовка ``Last-Event-ID`` для докачки потока.

Chat SSE serialization for the §5.3 ``ChatStreamEvent`` contract. Only an ad-hoc
private ``_sse()`` exists inline in the routers today, with no type validation.
Pure standard library:

* :class:`ChatStreamEvent`  — frozen ``{type, data, event_id}`` carrier.
* :data:`EVENT_TYPES`       — the allowed §5.3 event type names.
* :func:`validate_event`    — build an event, rejecting unknown types.
* :func:`to_sse_frame`      — render ``event:``/``data:`` (+ optional ``id:``).
* :func:`heartbeat_frame`   — SSE comment line to keep the connection alive.
* :func:`parse_last_event_id` — read the ``Last-Event-ID`` header value.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

# §5.3 event types — allowed values for a ChatStreamEvent.type.
EVENT_TYPES: frozenset[str] = frozenset(
    {"token", "tool_start", "tool_end", "evidence", "graph", "table", "gap", "error"}
)


@dataclass(frozen=True)
class ChatStreamEvent:
    """Одно событие потока §5.3 / one §5.3 chat-stream event.

    ``type`` — тип события (см. :data:`EVENT_TYPES`), ``data`` — полезная
    нагрузка, ``event_id`` — необязательный идентификатор для докачки (SSE ``id:``).
    """

    type: str
    data: dict
    event_id: str | None = None

    def as_dict(self) -> dict:
        """Return ``{"type", "data", "id"}`` (``id`` mirrors ``event_id``)."""
        return {"type": self.type, "data": self.data, "id": self.event_id}


def validate_event(type: str, data: dict, event_id: str | None = None) -> ChatStreamEvent:
    """Собрать событие, отклонив неизвестный тип / build an event, reject unknown type.

    :raises ValueError: если ``type`` не входит в :data:`EVENT_TYPES`.
    """
    if type not in EVENT_TYPES:
        raise ValueError(f"unknown ChatStreamEvent type: {type!r}")
    return ChatStreamEvent(type=type, data=data, event_id=event_id)


def to_sse_frame(ev: ChatStreamEvent) -> bytes:
    """Render an SSE frame: optional ``id:``, then ``event:`` + ``data:`` (§5.3)."""
    body = json.dumps(ev.data, ensure_ascii=False, default=str)
    prefix = f"id: {ev.event_id}\n" if ev.event_id is not None else ""
    return f"{prefix}event: {ev.type}\ndata: {body}\n\n".encode()


def heartbeat_frame(comment: str = "keep-alive") -> bytes:
    """Return an SSE comment line (``: <comment>``) used as a keep-alive ping."""
    return f": {comment}\n\n".encode()


def parse_last_event_id(header: str | None) -> str | None:
    """Разобрать заголовок ``Last-Event-ID`` / parse the ``Last-Event-ID`` header.

    Возвращает обрезанное непустое значение либо ``None`` (заголовок отсутствует
    или пустой после обрезки).
    """
    if header is None:
        return None
    trimmed = header.strip()
    return trimmed or None

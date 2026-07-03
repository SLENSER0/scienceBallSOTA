"""§13.21 human-in-the-loop interrupt stream event / событие прерывания в потоке.

Maps a pending §13.21 ``interrupt_request`` into a :class:`ChatStreamEvent`-shaped payload
for the UI clarification panel. ``interrupt_request.py`` builds the request and validates the
resume value; ``stream_events.py`` emits ``'done'`` even when input is awaited — neither of
them emits the interrupt event itself, so this module fills that gap.

Pure-python and deterministic: nothing here touches the graph store, so the module stays
unit-testable without a seeded Kuzu database (свойства узлов Kuzu не являются колонками
запроса / node props are not queryable columns — irrelevant here, no store access).

Surface:

* :class:`InterruptEvent` — frozen ``(type, data)`` event with ``type`` fixed to ``'interrupt'``
  and :meth:`~InterruptEvent.as_dict` for JSON-safe serialisation.
* :func:`is_awaiting_input` — True iff a state carries a truthy ``interrupt_request``.
* :func:`to_interrupt_event` — project an ``interrupt_request`` dict into an
  :class:`InterruptEvent`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Fixed event discriminator (фиксированный тип события / fixed event type).
_EVENT_TYPE: str = "interrupt"


@dataclass(frozen=True)
class InterruptEvent:
    """A UI clarification-panel event / событие панели уточнения интерфейса.

    ``type`` is always ``'interrupt'``; ``data`` carries ``{'kind', 'question', 'options'}``
    describing the pending human-in-the-loop request.
    """

    type: str
    data: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe projection / JSON-совместимая проекция ``{'type', 'data'}``."""
        return {"type": self.type, "data": dict(self.data)}


def is_awaiting_input(state: dict) -> bool:
    """True iff ``state`` awaits human input / ожидает ли состояние ввода человека.

    True exactly when ``state['interrupt_request']`` is truthy (отсутствие ключа или
    ``None`` — не ждём / missing key or ``None`` means not awaiting).
    """
    return bool(state.get("interrupt_request"))


def to_interrupt_event(interrupt_request: dict) -> InterruptEvent:
    """Map an ``interrupt_request`` dict to an :class:`InterruptEvent` / отобразить запрос.

    ``{'type', 'question', 'options', 'context'}`` becomes ``data`` ``{'kind', 'question',
    'options'}`` where ``kind`` is the request ``type`` and ``options`` defaults to ``[]``.
    """
    data: dict[str, Any] = {
        "kind": interrupt_request.get("type"),
        "question": interrupt_request.get("question"),
        "options": interrupt_request.get("options") or [],
    }
    return InterruptEvent(type=_EVENT_TYPE, data=data)

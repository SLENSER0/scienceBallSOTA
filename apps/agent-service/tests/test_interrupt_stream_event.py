"""§13.21 tests for interrupt stream event / тесты события прерывания в потоке."""

from __future__ import annotations

from agent_service.interrupt_stream_event import (
    InterruptEvent,
    is_awaiting_input,
    to_interrupt_event,
)


def test_is_awaiting_input_truthy() -> None:
    """(1) Truthy interrupt_request awaits input / непустой запрос — ждём ввода."""
    assert is_awaiting_input({"interrupt_request": {"type": "clarify_entity"}}) is True


def test_is_awaiting_input_missing() -> None:
    """(2) Missing key is not awaiting / отсутствие ключа — не ждём."""
    assert is_awaiting_input({}) is False


def test_is_awaiting_input_none() -> None:
    """(3) None interrupt_request is not awaiting / None — не ждём."""
    assert is_awaiting_input({"interrupt_request": None}) is False


def test_kind_maps_from_type() -> None:
    """(4) data['kind'] mirrors request type / kind повторяет тип запроса."""
    event = to_interrupt_event(
        {"type": "clarify_entity", "question": "Which Al-Cu?", "options": ["a", "b"]}
    )
    assert event.data["kind"] == "clarify_entity"


def test_options_preserved() -> None:
    """(5) Options pass through unchanged / опции проходят без изменений."""
    event = to_interrupt_event(
        {"type": "clarify_entity", "question": "Which Al-Cu?", "options": ["a", "b"]}
    )
    assert event.data["options"] == ["a", "b"]


def test_options_default_empty() -> None:
    """(6) Missing options default to [] / отсутствующие опции — []."""
    event = to_interrupt_event({"type": "clarify_entity", "question": "Which?"})
    assert event.data["options"] == []


def test_event_type_fixed() -> None:
    """(7) Event type is always 'interrupt' / тип события всегда 'interrupt'."""
    event = to_interrupt_event({"type": "clarify_entity", "question": "Which?"})
    assert event.type == "interrupt"


def test_as_dict_shape() -> None:
    """(8) as_dict yields {'type','data'} with mapped keys / форма as_dict."""
    event = to_interrupt_event(
        {"type": "clarify_entity", "question": "Which Al-Cu?", "options": ["a", "b"]}
    )
    assert event.as_dict() == {
        "type": "interrupt",
        "data": {"kind": "clarify_entity", "question": "Which Al-Cu?", "options": ["a", "b"]},
    }


def test_direct_construction() -> None:
    """InterruptEvent as_dict copies data / as_dict копирует данные."""
    event = InterruptEvent(type="interrupt", data={"kind": "confirm_claim"})
    dumped = event.as_dict()
    assert dumped == {"type": "interrupt", "data": {"kind": "confirm_claim"}}
    assert dumped["data"] is not event.data

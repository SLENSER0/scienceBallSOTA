"""§13.21 tests for human-in-the-loop interrupt request / тесты запроса на прерывание."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from agent_service.interrupt_request import (
    ALLOWED_TYPES,
    InterruptRequest,
    clarify_entity,
    validate_resume,
)


def test_bad_type_raises() -> None:
    """(1) Unknown type is rejected / неизвестный тип отклонён."""
    with pytest.raises(ValueError):
        InterruptRequest("bad_type", "q")


def test_clarify_entity_options() -> None:
    """(2) Options come from candidate canonical_ids / опции из canonical_id."""
    req = clarify_entity(
        "which?",
        [{"canonical_id": "Al-Cu"}, {"canonical_id": "Al-Mg"}],
    )
    assert req.options == ("Al-Cu", "Al-Mg")


def test_clarify_entity_label_fallback() -> None:
    """Label is used when canonical_id is absent / метка как запасной вариант."""
    req = clarify_entity("which?", [{"label": "Steel"}, {"canonical_id": "Al-Cu"}])
    assert req.options == ("Steel", "Al-Cu")


def test_as_dict_shape() -> None:
    """(3) as_dict options is a list, type preserved / options — список, тип сохранён."""
    req = clarify_entity("which?", [{"canonical_id": "Al-Cu"}])
    d = req.as_dict()
    assert isinstance(d["options"], list)
    assert d["type"] == "clarify_entity"
    assert d["question"] == "which?"


def test_validate_resume_accepts_offered() -> None:
    """(4) A listed option validates / указанная опция проходит проверку."""
    req = clarify_entity("which?", [{"canonical_id": "Al-Cu"}, {"canonical_id": "Al-Mg"}])
    assert validate_resume(req, "Al-Cu") is True


def test_validate_resume_rejects_unlisted() -> None:
    """(5) An unlisted value fails / значение вне списка не проходит."""
    req = clarify_entity("which?", [{"canonical_id": "Al-Cu"}, {"canonical_id": "Al-Mg"}])
    assert validate_resume(req, "Ti") is False


def test_empty_options_accept_anything() -> None:
    """(6) confirm_claim with no options accepts any value / пустые опции — любой ответ."""
    req = InterruptRequest("confirm_claim", "sure?")
    assert req.options == ()
    assert validate_resume(req, "yes") is True
    assert validate_resume(req, "literally anything") is True


def test_context_round_trips() -> None:
    """(7) context is preserved unchanged through as_dict / контекст без изменений."""
    candidates = [{"canonical_id": "Al-Cu", "score": 0.9}, {"canonical_id": "Al-Mg"}]
    req = clarify_entity("which?", candidates)
    assert req.as_dict()["context"] == {"candidates": candidates}


def test_allowed_types_membership() -> None:
    """All three allowed types construct / все три допустимых типа создаются."""
    assert set(ALLOWED_TYPES) == {"approve_query", "clarify_entity", "confirm_claim"}
    for kind in ALLOWED_TYPES:
        assert InterruptRequest(kind, "q?").type == kind


def test_frozen_immutable() -> None:
    """The dataclass is frozen / датакласс неизменяем."""
    req = InterruptRequest("approve_query", "run it?")
    with pytest.raises(FrozenInstanceError):
        req.type = "confirm_claim"  # type: ignore[misc]


def test_default_context_is_independent() -> None:
    """Default context does not leak between instances / контекст не общий."""
    a = InterruptRequest("confirm_claim", "a?")
    b = InterruptRequest("confirm_claim", "b?")
    a.context["x"] = 1
    assert b.context == {}

"""Тесты резолюции нового термина схемы — accept / map / reject (§16.6/§16.5)."""

from __future__ import annotations

import pytest

from kg_schema.schema_term_resolution import (
    TermResolution,
    apply_vocabulary,
    resolve_term,
)


def test_accept_bumps_version_and_accepts() -> None:
    """``accept`` -> ``accepted=True`` и версия ``current + 1`` (§16.6)."""
    res = resolve_term("newprop", "accept", ["a"], current_version=2)
    assert res.accepted is True
    assert res.vocabulary_version == 3
    assert res.action == "accept"
    assert res.mapped_to is None
    assert res.term == "newprop"


def test_accept_default_version() -> None:
    """Версия по умолчанию 1 -> после accept становится 2 (§16.6)."""
    res = resolve_term("x", "accept", ["a"])
    assert res.vocabulary_version == 2
    assert res.accepted is True


def test_map_to_existing_term() -> None:
    """``map`` на существующий термин: не принят, версия не меняется (§16.5)."""
    res = resolve_term("t", "map", ["a"], mapped_to="a")
    assert res.accepted is False
    assert res.mapped_to == "a"
    assert res.vocabulary_version == 1
    assert res.action == "map"


def test_map_to_missing_term_raises() -> None:
    """``map`` на отсутствующий термин -> ValueError (§16.5)."""
    with pytest.raises(ValueError):
        resolve_term("t", "map", ["a"], mapped_to="zzz")


def test_map_without_target_raises() -> None:
    """``map`` без ``mapped_to`` -> ValueError (§16.5)."""
    with pytest.raises(ValueError):
        resolve_term("t", "map", ["a"])


def test_reject_not_accepted() -> None:
    """``reject`` -> ``accepted=False`` и версия не меняется (§16.5)."""
    res = resolve_term("t", "reject", ["a"], current_version=5)
    assert res.accepted is False
    assert res.vocabulary_version == 5
    assert res.action == "reject"
    assert res.mapped_to is None


def test_invalid_action_raises() -> None:
    """Неизвестное действие -> ValueError (§16.6)."""
    with pytest.raises(ValueError):
        resolve_term("t", "bogus", ["a"])


def test_apply_vocabulary_accept_adds_term() -> None:
    """accept-решение добавляет термин в отсортированный словарь (§16.6)."""
    res = resolve_term("b", "accept", ["a"])
    assert apply_vocabulary(["a"], res) == ["a", "b"]


def test_apply_vocabulary_reject_no_change() -> None:
    """reject-решение не меняет словарь (§16.5)."""
    res = resolve_term("b", "reject", ["a"])
    assert apply_vocabulary(["a"], res) == ["a"]


def test_apply_vocabulary_map_no_change() -> None:
    """map-решение не добавляет термин (§16.5)."""
    res = resolve_term("b", "map", ["a"], mapped_to="a")
    assert apply_vocabulary(["a"], res) == ["a"]


def test_apply_vocabulary_dedup_and_sort() -> None:
    """Дубликаты схлопываются, результат отсортирован (§16.6)."""
    res = resolve_term("a", "accept", ["a"])
    assert apply_vocabulary(["c", "a", "b"], res) == ["a", "b", "c"]


def test_as_dict_echoes_action() -> None:
    """``as_dict()['action']`` повторяет исходное действие (§16.6)."""
    res = resolve_term("newprop", "accept", ["a"], current_version=2)
    d = res.as_dict()
    assert d["action"] == "accept"
    assert d["accepted"] is True
    assert d["vocabulary_version"] == 3
    assert d["term"] == "newprop"
    assert d["mapped_to"] is None


def test_as_dict_map_action() -> None:
    """``as_dict()`` для map несёт ``mapped_to`` и ``accepted=False`` (§16.5)."""
    res = resolve_term("t", "map", ["a"], mapped_to="a")
    d = res.as_dict()
    assert d["action"] == "map"
    assert d["mapped_to"] == "a"
    assert d["accepted"] is False


def test_frozen_dataclass() -> None:
    """:class:`TermResolution` неизменяем (frozen) (§16.6)."""
    res = resolve_term("t", "reject", ["a"])
    with pytest.raises((AttributeError, TypeError)):
        res.term = "other"  # type: ignore[misc]
    assert isinstance(res, TermResolution)

"""Tests for the persistable comparison view (§24.13).

Проверяем нормализацию весов, валидацию ключей и round-trip сериализацию
пользовательского view критериев/весов.
"""

from __future__ import annotations

import math

import pytest

from kg_retrievers.comparison_view import (
    ComparisonView,
    build_view,
    normalize_weights,
)


def test_normalize_preserves_ratios() -> None:
    """(1) {'a':1,'b':3} → {'a':0.25,'b':0.75} — пропорции сохранены."""
    out = normalize_weights({"a": 1.0, "b": 3.0})
    assert out == {"a": 0.25, "b": 0.75}


def test_build_view_rejects_extra_weight_key() -> None:
    """(2) вес по ключу не из критериев → ValueError."""
    with pytest.raises(ValueError):
        build_view(
            "v1",
            ("a", "b"),
            {"a": 1.0, "b": 1.0, "c": 1.0},
            "user1",
            "2026-07-03T00:00:00Z",
        )


def test_build_view_rejects_missing_weight() -> None:
    """(3) у критерия отсутствует вес — не по умолчанию, а ValueError."""
    with pytest.raises(ValueError):
        build_view("v1", ("a", "b"), {"a": 1.0}, "user1", "2026-07-03T00:00:00Z")


def test_all_zero_weights_equal_split() -> None:
    """(4) все нули → равномерное распределение с суммой 1.0."""
    view = build_view("v1", ("a", "b", "c"), {"a": 0.0, "b": 0.0, "c": 0.0}, "u", "t")
    assert view.weights == {"a": 1 / 3, "b": 1 / 3, "c": 1 / 3}
    assert math.isclose(sum(view.weights.values()), 1.0, abs_tol=1e-9)


def test_stored_weights_sum_to_one() -> None:
    """(5) сохранённые веса суммируются к 1.0 в пределах 1e-9."""
    view = build_view("v1", ("a", "b", "c"), {"a": 2.0, "b": 5.0, "c": 3.0}, "u", "t")
    assert math.isclose(sum(view.weights.values()), 1.0, abs_tol=1e-9)
    assert math.isclose(view.weights["a"], 0.2, abs_tol=1e-9)
    assert math.isclose(view.weights["b"], 0.5, abs_tol=1e-9)
    assert math.isclose(view.weights["c"], 0.3, abs_tol=1e-9)


def test_as_dict_from_dict_round_trip() -> None:
    """(6) as_dict/from_dict round-trip дают равный объект."""
    view = build_view(
        "v42", ("cost", "quality"), {"cost": 1.0, "quality": 3.0}, "alice", "2026-01-01T12:00:00Z"
    )
    restored = ComparisonView.from_dict(view.as_dict())
    assert restored == view
    assert restored.as_dict() == view.as_dict()


def test_criteria_order_preserved_and_deduped() -> None:
    """(7) порядок критериев сохранён, дубликаты удалены (первое вхождение)."""
    view = build_view("v1", ["b", "a", "b", "c", "a"], {"a": 1.0, "b": 1.0, "c": 2.0}, "u", "t")
    assert view.criteria == ("b", "a", "c")
    assert math.isclose(sum(view.weights.values()), 1.0, abs_tol=1e-9)


def test_single_criterion_weight_one() -> None:
    """(8) единственный критерий → вес 1.0."""
    view = build_view("v1", ("only",), {"only": 7.0}, "u", "t")
    assert view.criteria == ("only",)
    assert view.weights == {"only": 1.0}


def test_normalize_empty_all_zero() -> None:
    """all-zero edge: пустой словарь остаётся пустым."""
    assert normalize_weights({}) == {}


def test_view_is_frozen() -> None:
    """ComparisonView неизменяем / frozen dataclass."""
    view = build_view("v1", ("a",), {"a": 1.0}, "u", "t")
    with pytest.raises(AttributeError):
        view.view_id = "x"  # type: ignore[misc]

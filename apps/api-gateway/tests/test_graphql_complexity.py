"""Tests for the GraphQL complexity/depth guard (§14.13).

Ручной пересчёт: глубина = максимальная вложенность ``{``/``}``, число полей =
идентификаторы внутри selection set-ов. Hand-checkable: depth is the maximum
brace nesting, field_count counts identifiers inside selection sets.
"""

from __future__ import annotations

from api_gateway.graphql_complexity import (
    ComplexityResult,
    estimate_complexity,
    is_within_limits,
)


def test_depth_single_level() -> None:
    """``{ a b }`` — одна пара скобок → глубина 1 / one brace pair → depth 1."""
    assert estimate_complexity("{ a b }").depth == 1


def test_depth_three_levels() -> None:
    """``{a{b{c}}}`` — тройная вложенность → глубина 3 / triple nesting → depth 3."""
    assert estimate_complexity("{a{b{c}}}").depth == 3


def test_field_count_three_flat() -> None:
    """``{a b c}`` — три поля в одном selection set / three fields → count 3."""
    assert estimate_complexity("{a b c}").field_count == 3


def test_field_count_counts_all_nested() -> None:
    """``{a{b{c}}}`` — три идентификатора a,b,c → count 3 / all nested fields counted."""
    assert estimate_complexity("{a{b{c}}}").field_count == 3


def test_is_within_limits_trivial_true() -> None:
    """``{a}`` — тривиальный запрос в пределах лимитов / within default limits."""
    assert is_within_limits("{a}") is True


def test_is_within_limits_depth_exceeded() -> None:
    """``{a{b{c}}}`` при max_depth=2 → отклонить / depth 3 > 2 → rejected."""
    assert is_within_limits("{a{b{c}}}", max_depth=2) is False


def test_is_within_limits_depth_ok_at_boundary() -> None:
    """Глубина ровно на границе (3 == 3) допустима / depth at the boundary passes."""
    assert is_within_limits("{a{b{c}}}", max_depth=3) is True


def test_is_within_limits_fields_exceeded() -> None:
    """Число полей 3 > max_fields=2 → отклонить / field count over limit → rejected."""
    assert is_within_limits("{a b c}", max_fields=2) is False


def test_over_limit_default_false() -> None:
    """``{a{b{c}}}`` при дефолтном max_depth=10 → over_limit False / not over limit."""
    assert estimate_complexity("{a{b{c}}}").over_limit is False


def test_over_limit_default_true_when_deep() -> None:
    """Глубина 11 > дефолт 10 → over_limit True / depth 11 exceeds default 10."""
    deep = "{" * 11 + "x" + "}" * 11
    result = estimate_complexity(deep)
    assert result.depth == 11
    assert result.over_limit is True


def test_over_limit_default_true_when_many_fields() -> None:
    """201 поле > дефолт 200 → over_limit True / too many fields exceeds default."""
    query = "{" + " ".join(f"f{i}" for i in range(201)) + "}"
    result = estimate_complexity(query)
    assert result.field_count == 201
    assert result.over_limit is True


def test_result_as_dict() -> None:
    """``as_dict`` отдаёт плоский маппинг / flat mapping round-trip."""
    assert ComplexityResult(3, 5, False).as_dict()["depth"] == 3
    assert ComplexityResult(3, 5, False).as_dict() == {
        "depth": 3,
        "field_count": 5,
        "over_limit": False,
    }


def test_result_is_frozen() -> None:
    """Заморожен: присваивание падает / frozen dataclass forbids mutation."""
    import dataclasses

    result = estimate_complexity("{a}")
    try:
        result.depth = 99  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("ComplexityResult should be frozen")


def test_empty_query() -> None:
    """Пустой запрос → нулевые метрики / empty query yields zeroed metrics."""
    result = estimate_complexity("")
    assert result.depth == 0
    assert result.field_count == 0
    assert result.over_limit is False


def test_arguments_do_not_break_depth() -> None:
    """Поле с аргументами и вложенностью / field with args plus nesting.

    ``{ user(id: 1) { name posts { title } } }`` — глубина 3, поля:
    user, id, name, posts, title = 5 (аргумент id считается идентификатором).
    """
    result = estimate_complexity("{ user(id: 1) { name posts { title } } }")
    assert result.depth == 3
    assert result.field_count == 5

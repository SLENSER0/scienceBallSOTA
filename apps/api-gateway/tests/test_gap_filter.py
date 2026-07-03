"""Тесты фильтра пробелов ``GET /gaps`` (§14.8).

Hand-checkable tests for :mod:`api_gateway.gap_filter`: the §11.1 type
constants, status validation, and the :func:`matches` predicate.
"""

from __future__ import annotations

import pytest
from api_gateway.gap_filter import (
    GAP_STATUSES,
    GAP_TYPES,
    GapFilter,
    matches,
    parse_gap_filter,
)


def test_gap_types_has_nine_members() -> None:
    """§11.1 определяет ровно девять типов пробелов / exactly nine types."""
    assert len(GAP_TYPES) == 9
    assert "orphan_entity" in GAP_TYPES
    assert "missing_property_value" in GAP_TYPES


def test_gap_statuses_members() -> None:
    """Статусы пробела ограничены тремя значениями / three statuses (§14.8)."""
    assert frozenset({"open", "known", "irrelevant"}) == GAP_STATUSES


def test_parse_single_type() -> None:
    """Один валидный тип разбирается в одноэлементный кортеж / single type."""
    f = parse_gap_filter(["orphan_entity"], None)
    assert f.types == ("orphan_entity",)
    assert f.status is None


def test_parse_none_types_yields_empty_tuple() -> None:
    """``types`` ``None`` даёт пустой кортеж / empty tuple for None types."""
    f = parse_gap_filter(None, None)
    assert f.types == ()
    assert f.status is None


def test_parse_bogus_type_raises() -> None:
    """Неизвестный тип отвергается / unknown type raises ValueError."""
    with pytest.raises(ValueError):
        parse_gap_filter(["bogus"], None)


def test_parse_bogus_status_raises() -> None:
    """Неизвестный статус отвергается / unknown status raises ValueError."""
    with pytest.raises(ValueError):
        parse_gap_filter(None, "weird")


def test_parse_valid_status() -> None:
    """Валидный статус сохраняется / valid status is retained."""
    f = parse_gap_filter(["missing_unit"], "known")
    assert f.status == "known"
    assert f.types == ("missing_unit",)


def test_matches_type_and_status() -> None:
    """Совпадение по типу (статус игнорируется при None) / type match."""
    gap = {"type": "orphan_entity", "status": "open"}
    assert matches(gap, GapFilter(("orphan_entity",), None)) is True


def test_matches_type_mismatch() -> None:
    """Несовпадение типа отбрасывает пробел / type mismatch rejects."""
    gap = {"type": "missing_unit"}
    assert matches(gap, GapFilter(("orphan_entity",), None)) is False


def test_matches_status_mismatch() -> None:
    """Пустые типы совпадают со всеми, но статус фильтрует / status filters."""
    gap = {"type": "orphan_entity", "status": "known"}
    assert matches(gap, GapFilter((), "open")) is False


def test_matches_empty_types_matches_all() -> None:
    """Пустой кортеж типов совпадает с любым типом / empty types match all."""
    gap = {"type": "low_coverage_material", "status": "open"}
    assert matches(gap, GapFilter((), "open")) is True


def test_matches_status_none_matches_all() -> None:
    """``status`` ``None`` совпадает с любым статусом / None status matches all."""
    gap = {"type": "unverified_claim", "status": "irrelevant"}
    assert matches(gap, GapFilter(("unverified_claim",), None)) is True


def test_matches_absent_type_fails_active_filter() -> None:
    """Отсутствующий тип не проходит активный фильтр / absent field fails."""
    gap = {"status": "open"}
    assert matches(gap, GapFilter(("orphan_entity",), None)) is False


def test_as_dict_roundtrip() -> None:
    """``as_dict`` даёт wire-форму с опциональным статусом / wire form."""
    assert GapFilter(("orphan_entity",), "open").as_dict() == {
        "types": ["orphan_entity"],
        "status": "open",
    }
    assert GapFilter((), None).as_dict() == {"types": []}

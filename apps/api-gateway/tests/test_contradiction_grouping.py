"""Тесты группировки/фильтрации противоречий (§5.2.7, §14.8).

Hand-checkable tests for :mod:`api_gateway.contradiction_grouping`: filtering by
material, grouping by material×property, claim-id deduplication, count-descending
sort, and the :meth:`ContradictionGroup.as_dict` wire form.
"""

from __future__ import annotations

from api_gateway.contradiction_grouping import (
    ContradictionGroup,
    filter_contradictions,
    group_contradictions,
)


def test_two_rows_same_pair_single_group() -> None:
    """Две строки M×P дают одну группу count==2 / single group of two."""
    rows = [
        {"material": "M", "property": "P", "claim_id": "c1"},
        {"material": "M", "property": "P", "claim_id": "c2"},
    ]
    groups = group_contradictions(rows)
    assert len(groups) == 1
    assert groups[0].count == 2
    assert groups[0].claim_ids == ("c1", "c2")


def test_rows_spanning_two_properties_two_groups() -> None:
    """Строки по двум свойствам дают две группы / two properties → two groups."""
    rows = [
        {"material": "M", "property": "P1", "claim_id": "c1"},
        {"material": "M", "property": "P2", "claim_id": "c2"},
    ]
    groups = group_contradictions(rows)
    assert len(groups) == 2


def test_duplicate_claim_id_counted_once() -> None:
    """Повторный claim_id считается один раз / dedup preserves order."""
    rows = [
        {"material": "M", "property": "P", "claim_id": "c1"},
        {"material": "M", "property": "P", "claim_id": "c1"},
        {"material": "M", "property": "P", "claim_id": "c2"},
    ]
    groups = group_contradictions(rows)
    assert len(groups) == 1
    assert groups[0].claim_ids == ("c1", "c2")
    assert groups[0].count == 2


def test_groups_sorted_count_desc_then_material_asc() -> None:
    """Группы сортируются по count-убыв., затем material-возр. / sort order."""
    rows = [
        {"material": "B", "property": "P", "claim_id": "c1"},
        {"material": "A", "property": "P", "claim_id": "c2"},
        {"material": "A", "property": "P", "claim_id": "c3"},
    ]
    groups = group_contradictions(rows)
    # A has count 2 (first), B has count 1.
    assert [g.material for g in groups] == ["A", "B"]
    assert groups[0].count == 2
    assert groups[1].count == 1


def test_sort_material_asc_tiebreak_on_equal_count() -> None:
    """При равном count материал по возрастанию / material asc tiebreak."""
    rows = [
        {"material": "Z", "property": "P", "claim_id": "c1"},
        {"material": "A", "property": "P", "claim_id": "c2"},
    ]
    groups = group_contradictions(rows)
    assert [g.material for g in groups] == ["A", "Z"]


def test_filter_by_material_returns_only_matching() -> None:
    """filter_contradictions material='M' отдаёт только M / only M rows."""
    rows = [
        {"material": "M", "property": "P", "claim_id": "c1"},
        {"material": "N", "property": "P", "claim_id": "c2"},
    ]
    out = filter_contradictions(rows, material="M")
    assert len(out) == 1
    assert out[0]["claim_id"] == "c1"


def test_filter_by_property_returns_only_matching() -> None:
    """filter_contradictions property='P' отдаёт только P / only P rows."""
    rows = [
        {"material": "M", "property": "P", "claim_id": "c1"},
        {"material": "M", "property": "Q", "claim_id": "c2"},
    ]
    out = filter_contradictions(rows, property="P")
    assert len(out) == 1
    assert out[0]["property"] == "P"


def test_filter_no_filters_returns_all() -> None:
    """Без фильтров возвращаются все строки / no filters returns all."""
    rows = [
        {"material": "M", "property": "P", "claim_id": "c1"},
        {"material": "N", "property": "Q", "claim_id": "c2"},
    ]
    out = filter_contradictions(rows)
    assert len(out) == 2


def test_as_dict_wire_form() -> None:
    """as_dict отдаёт count и список claim_ids / wire form has count."""
    g = ContradictionGroup(material="M", property="P", claim_ids=("c1", "c2"), count=2)
    d = g.as_dict()
    assert d["count"] == 2
    assert d["material"] == "M"
    assert d["property"] == "P"
    assert d["claim_ids"] == ["c1", "c2"]


def test_group_is_frozen() -> None:
    """Группа неизменяема / frozen dataclass rejects mutation."""
    g = ContradictionGroup(material="M", property="P", claim_ids=("c1",), count=1)
    try:
        g.count = 5  # type: ignore[misc]
    except (AttributeError, TypeError):
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("ContradictionGroup should be immutable")

"""Tests for §13.16 contradiction grouping / тесты группировки противоречий."""

from __future__ import annotations

from agent_service.contradiction_group import (
    ContradictionGroup,
    group_contradictions,
    has_contradictions,
)


def _m(material: str, regime: str, property_: str, value: float, source_id: str) -> dict:
    """Build one raw measurement dict / собрать сырое измерение."""
    return {
        "material": material,
        "regime": regime,
        "property": property_,
        "value": value,
        "source_id": source_id,
    }


def test_divergent_values_form_one_group_with_spread() -> None:
    """(1) 148 vs 160 on a shared key -> one group, spread 12."""
    groups = group_contradictions(
        [
            _m("Ti-6Al-4V", "as-built", "hardness", 148.0, "s1"),
            _m("Ti-6Al-4V", "as-built", "hardness", 160.0, "s2"),
        ]
    )
    assert len(groups) == 1
    assert groups[0].values == (148.0, 160.0)
    assert groups[0].spread == 12.0


def test_identical_values_form_no_group() -> None:
    """(2) two identical readings are agreement, not a contradiction."""
    groups = group_contradictions(
        [
            _m("Ti-6Al-4V", "as-built", "hardness", 150.0, "s1"),
            _m("Ti-6Al-4V", "as-built", "hardness", 150.0, "s2"),
        ]
    )
    assert groups == []


def test_different_keys_not_merged() -> None:
    """(3) distinct (material, regime, property) keys stay separate."""
    groups = group_contradictions(
        [
            _m("Ti-6Al-4V", "as-built", "hardness", 148.0, "s1"),
            _m("Ti-6Al-4V", "as-built", "hardness", 160.0, "s2"),
            _m("Inconel-718", "aged", "yield", 1000.0, "s3"),
            _m("Inconel-718", "aged", "yield", 1100.0, "s4"),
        ]
    )
    assert len(groups) == 2
    keys = {(g.material, g.regime, g.property) for g in groups}
    assert keys == {
        ("Ti-6Al-4V", "as-built", "hardness"),
        ("Inconel-718", "aged", "yield"),
    }


def test_source_ids_deduped_and_sorted() -> None:
    """(4) duplicate source_ids collapse and come back sorted."""
    groups = group_contradictions(
        [
            _m("Ti-6Al-4V", "as-built", "hardness", 148.0, "s3"),
            _m("Ti-6Al-4V", "as-built", "hardness", 160.0, "s1"),
            _m("Ti-6Al-4V", "as-built", "hardness", 155.0, "s1"),
        ]
    )
    assert len(groups) == 1
    assert groups[0].source_ids == ("s1", "s3")


def test_groups_sorted_by_spread_descending() -> None:
    """(5) the widest spread surfaces first."""
    groups = group_contradictions(
        [
            _m("A", "r", "p", 10.0, "s1"),
            _m("A", "r", "p", 12.0, "s2"),
            _m("B", "r", "p", 10.0, "s3"),
            _m("B", "r", "p", 100.0, "s4"),
        ]
    )
    spreads = [g.spread for g in groups]
    assert spreads == sorted(spreads, reverse=True)
    assert groups[0].material == "B"
    assert groups[0].spread == 90.0


def test_has_contradictions_truthiness() -> None:
    """(6) True for a non-empty result, False for []."""
    non_empty = [
        ContradictionGroup(
            material="A",
            regime="r",
            property="p",
            values=(1.0, 2.0),
            spread=1.0,
            source_ids=("s1", "s2"),
        )
    ]
    assert has_contradictions(non_empty) is True
    assert has_contradictions([]) is False


def test_as_dict_values_is_list() -> None:
    """(7) as_dict() emits values (and source_ids) as lists."""
    group = ContradictionGroup(
        material="A",
        regime="r",
        property="p",
        values=(1.0, 2.0),
        spread=1.0,
        source_ids=("s1", "s2"),
    )
    d = group.as_dict()
    assert isinstance(d["values"], list)
    assert d["values"] == [1.0, 2.0]
    assert isinstance(d["source_ids"], list)
    assert d["source_ids"] == ["s1", "s2"]

"""Tests for :mod:`kg_common.partition_mapping` — тесты маппинга партиций (§9.3)."""

from __future__ import annotations

import pytest

from kg_common.partition_mapping import (
    PartitionDependency,
    day_to_month,
    resolve_dependency,
)


def test_day_to_month_basic() -> None:
    """`'2026-07-03' -> '2026-07'` — день сворачивается в месяц."""
    assert day_to_month("2026-07-03") == "2026-07"
    assert day_to_month("2026-12-31") == "2026-12"
    assert day_to_month("2000-01-01") == "2000-01"


def test_day_to_month_rejects_bad_keys() -> None:
    """Non ``YYYY-MM-DD`` keys raise — некорректный ключ отвергается."""
    for bad in ("2026-07", "2026", "2026-07-03-04", "--", ""):
        with pytest.raises(ValueError):
            day_to_month(bad)


def test_identity_present() -> None:
    """Identity keeps the key when it exists in the universe."""
    dep = resolve_dependency("identity", "doc-1", ("doc-1", "doc-2"))
    assert dep.upstream_keys == ("doc-1",)
    assert dep.downstream_key == "doc-1"


def test_identity_absent() -> None:
    """Identity yields empty deps when the key is missing from the universe."""
    dep = resolve_dependency("identity", "doc-9", ("doc-1",))
    assert dep.upstream_keys == ()


def test_all_fan_in_order_preserved() -> None:
    """`all` fans in over the whole universe, order preserved — веерный вход."""
    dep = resolve_dependency("all", "gap_scan", ("d1", "d2", "d3"))
    assert dep.upstream_keys == ("d1", "d2", "d3")
    # Order really is the universe's order, not sorted:
    dep2 = resolve_dependency("all", "retrieval_eval", ("d3", "d1", "d2"))
    assert dep2.upstream_keys == ("d3", "d1", "d2")


def test_all_empty_universe() -> None:
    """`all` over an empty universe yields no deps."""
    dep = resolve_dependency("all", "gap_scan", ())
    assert dep.upstream_keys == ()


def test_time_to_day_selects_month() -> None:
    """`time_to_day` selects day keys of the matching month, order preserved."""
    dep = resolve_dependency(
        "time_to_day",
        "2026-07",
        ("2026-07-01", "2026-07-02", "2026-08-01"),
    )
    assert dep.upstream_keys == ("2026-07-01", "2026-07-02")


def test_time_to_day_no_match() -> None:
    """`time_to_day` yields empty deps when no day falls in the month."""
    dep = resolve_dependency("time_to_day", "2026-09", ("2026-07-01", "2026-08-01"))
    assert dep.upstream_keys == ()


def test_unknown_kind_raises() -> None:
    """An unknown mapping kind raises ``ValueError`` — неизвестный вид."""
    with pytest.raises(ValueError):
        resolve_dependency("bogus", "x", ("x",))


def test_as_dict_roundtrip() -> None:
    """`as_dict` is JSON-shaped with a list of upstream keys."""
    dep = resolve_dependency("identity", "x", ("x",))
    assert dep.as_dict() == {"downstream_key": "x", "upstream_keys": ["x"]}


def test_as_dict_all() -> None:
    """`as_dict` reflects a fan-in dependency as an ordered list."""
    dep = resolve_dependency("all", "gap_scan", ("d1", "d2"))
    assert dep.as_dict() == {
        "downstream_key": "gap_scan",
        "upstream_keys": ["d1", "d2"],
    }


def test_dependency_is_frozen() -> None:
    """The dataclass is frozen — мутировать нельзя."""
    dep = PartitionDependency(downstream_key="d", upstream_keys=("u",))
    with pytest.raises(AttributeError):
        dep.downstream_key = "other"  # type: ignore[misc]

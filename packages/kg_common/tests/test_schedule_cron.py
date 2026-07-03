"""Tests for kg_common.schedule_cron — cron parsing/next-run/catch-up (§9.5)."""

from __future__ import annotations

from datetime import datetime

import pytest

from kg_common.schedule_cron import (
    CronSpec,
    matches,
    missed_ticks,
    next_after,
    parse_cron,
)


def test_parse_daily_two_am() -> None:
    spec = parse_cron("0 2 * * *")
    assert spec.hour == frozenset({2})
    assert spec.minute == frozenset({0})
    # Unrestricted fields expand to their full ranges.
    assert spec.dom == frozenset(range(1, 32))
    assert spec.month == frozenset(range(1, 13))
    assert spec.dow == frozenset(range(0, 7))


def test_parse_step_minutes() -> None:
    assert parse_cron("*/15 * * * *").minute == frozenset({0, 15, 30, 45})


def test_parse_range_minutes() -> None:
    assert parse_cron("1-3 * * * *").minute == frozenset({1, 2, 3})


def test_parse_range_step_and_list() -> None:
    # a-b/n
    assert parse_cron("0-10/5 * * * *").minute == frozenset({0, 5, 10})
    # comma list
    assert parse_cron("1,5,9 * * * *").minute == frozenset({1, 5, 9})
    # a/n walks to field max
    assert parse_cron("55/1 * * * *").minute == frozenset({55, 56, 57, 58, 59})


def test_parse_dow_seven_is_sunday() -> None:
    assert parse_cron("0 0 * * 7").dow == frozenset({0})
    assert parse_cron("0 0 * * 0").dow == frozenset({0})


def test_as_dict_sorted_lists() -> None:
    spec = parse_cron("0 2 * * *")
    d = spec.as_dict()
    assert d["hour"] == [2]
    assert d["minute"] == [0]
    assert d["month"] == list(range(1, 13))
    assert isinstance(d["dom"], list)


def test_spec_is_frozen() -> None:
    spec = parse_cron("0 2 * * *")
    with pytest.raises((AttributeError, TypeError)):
        spec.hour = frozenset({3})  # type: ignore[misc]


def test_matches_daily_two_am() -> None:
    spec = parse_cron("0 2 * * *")
    assert matches(spec, datetime(2026, 7, 3, 2, 0)) is True
    # Wrong hour.
    assert matches(spec, datetime(2026, 7, 3, 1, 0)) is False
    # Right hour, wrong minute.
    assert matches(spec, datetime(2026, 7, 3, 2, 1)) is False


def test_matches_step_minutes() -> None:
    spec = parse_cron("*/15 * * * *")
    assert matches(spec, datetime(2026, 7, 3, 10, 15)) is True
    assert matches(spec, datetime(2026, 7, 3, 10, 30)) is True
    assert matches(spec, datetime(2026, 7, 3, 10, 7)) is False


def test_matches_dow_or_dom_semantics() -> None:
    # 2026-07-03 is a Friday (cron dow 5). dom=15 OR dow=5 → both restricted.
    spec = parse_cron("0 0 15 * 5")
    assert matches(spec, datetime(2026, 7, 3, 0, 0)) is True  # dow hit
    assert matches(spec, datetime(2026, 7, 15, 0, 0)) is True  # dom hit
    # 2026-07-10 is Friday too, so dow still matches; use a non-Fri non-15th.
    assert matches(spec, datetime(2026, 7, 16, 0, 0)) is False


def test_next_after_daily_rolls_to_next_day() -> None:
    spec = parse_cron("0 2 * * *")
    assert next_after(spec, datetime(2026, 7, 3, 2, 0)) == datetime(2026, 7, 4, 2, 0)


def test_next_after_step_minutes() -> None:
    spec = parse_cron("*/15 * * * *")
    assert next_after(spec, datetime(2026, 7, 3, 10, 7)) == datetime(2026, 7, 3, 10, 15)


def test_next_after_is_strictly_after() -> None:
    spec = parse_cron("*/15 * * * *")
    # Already on a boundary → must advance to the following tick.
    assert next_after(spec, datetime(2026, 7, 3, 10, 15)) == datetime(2026, 7, 3, 10, 30)


def test_next_after_ignores_seconds() -> None:
    spec = parse_cron("*/15 * * * *")
    got = next_after(spec, datetime(2026, 7, 3, 10, 7, 42))
    assert got == datetime(2026, 7, 3, 10, 15)


def test_missed_ticks_count() -> None:
    spec = parse_cron("0 2 * * *")
    ticks = missed_ticks(spec, datetime(2026, 7, 1, 2, 0), datetime(2026, 7, 3, 3, 0))
    assert len(ticks) == 2
    assert ticks == [datetime(2026, 7, 2, 2, 0), datetime(2026, 7, 3, 2, 0)]


def test_missed_ticks_inclusive_of_now() -> None:
    spec = parse_cron("0 2 * * *")
    # now is exactly on a tick → included.
    ticks = missed_ticks(spec, datetime(2026, 7, 1, 2, 0), datetime(2026, 7, 3, 2, 0))
    assert ticks[-1] == datetime(2026, 7, 3, 2, 0)
    assert len(ticks) == 2


def test_missed_ticks_exclusive_of_last() -> None:
    spec = parse_cron("0 2 * * *")
    # last is on a tick; that tick must not be re-emitted.
    ticks = missed_ticks(spec, datetime(2026, 7, 1, 2, 0), datetime(2026, 7, 1, 23, 0))
    assert ticks == []


def test_missed_ticks_empty_when_now_before_last() -> None:
    spec = parse_cron("*/15 * * * *")
    ticks = missed_ticks(spec, datetime(2026, 7, 3, 10, 0), datetime(2026, 7, 3, 9, 0))
    assert ticks == []


def test_parse_rejects_wrong_field_count() -> None:
    with pytest.raises(ValueError):
        parse_cron("0 2 * *")


def test_parse_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        parse_cron("99 * * * *")


def test_parse_rejects_bad_step() -> None:
    with pytest.raises(ValueError):
        parse_cron("*/0 * * * *")


def test_cronspec_direct_as_dict() -> None:
    spec = CronSpec(
        minute=frozenset({0}),
        hour=frozenset({2}),
        dom=frozenset({1}),
        month=frozenset({1}),
        dow=frozenset({0}),
    )
    assert spec.as_dict()["hour"] == [2]

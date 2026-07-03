"""Tests for canonical time/duration conversion (§7.2/§8).

RU: Проверяем перевод в часы/секунды по фиксированным множителям.
EN: Hand-checkable conversions: 2 h = 7200 s, 90 min = 1.5 h, 1 day = 24 h.
"""

from __future__ import annotations

import pytest

from kg_common.units.time_duration import (
    DURATION_UNITS,
    Duration,
    UnknownDurationUnitError,
    convert_duration,
    to_hours,
    to_seconds,
)


def test_to_seconds_hours() -> None:
    assert to_seconds(2, "h") == 7200.0


def test_to_seconds_minute() -> None:
    assert to_seconds(1, "min") == 60.0


def test_to_seconds_milliseconds() -> None:
    # 500 ms = 0.5 s.
    assert to_seconds(500, "ms") == 0.5


def test_to_hours_minutes() -> None:
    # 90 min = 1.5 h.
    assert to_hours(90, "min") == 1.5


def test_to_hours_day() -> None:
    assert to_hours(1, "day") == 24.0


def test_to_hours_identity() -> None:
    assert to_hours(1, "h") == 1.0


def test_second_aliases() -> None:
    assert to_seconds(3, "s") == to_seconds(3, "sec") == 3.0


def test_hour_aliases() -> None:
    assert to_hours(1, "hr") == to_hours(1, "hour") == 1.0


def test_week_factor() -> None:
    # 1 week = 168 h = 604800 s.
    assert to_hours(1, "week") == 168.0
    assert to_seconds(1, "week") == 604800.0


def test_convert_duration_day_to_hours() -> None:
    d = convert_duration(1, "day", "h")
    assert isinstance(d, Duration)
    assert d.hours == 24.0
    assert d.seconds == 86400.0
    assert d.value_raw == 1
    assert d.from_unit == "day"


def test_duration_as_dict() -> None:
    d = convert_duration(2, "h", "min")
    assert d.as_dict() == {
        "value_raw": 2,
        "from_unit": "h",
        "hours": 2.0,
        "seconds": 7200.0,
    }


def test_duration_is_frozen() -> None:
    d = convert_duration(1, "h", "h")
    with pytest.raises((AttributeError, TypeError)):
        d.hours = 99.0  # type: ignore[misc]


def test_unknown_from_unit_raises() -> None:
    with pytest.raises(UnknownDurationUnitError):
        to_seconds(1, "MPa")


def test_unknown_hours_unit_raises() -> None:
    with pytest.raises(UnknownDurationUnitError):
        to_hours(1, "MPa")


def test_unknown_target_unit_raises() -> None:
    with pytest.raises(UnknownDurationUnitError):
        convert_duration(1, "h", "MPa")


def test_error_carries_unit() -> None:
    with pytest.raises(UnknownDurationUnitError) as exc:
        to_seconds(1, "furlong")
    assert exc.value.unit == "furlong"


def test_units_tuple_membership() -> None:
    for unit in ("s", "sec", "ms", "min", "h", "hr", "hour", "day", "week"):
        assert unit in DURATION_UNITS

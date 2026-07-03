"""Tests for :mod:`kg_common.sensor_cursor` — §9.6 sensor idempotent cursor."""

from __future__ import annotations

from kg_common.sensor_cursor import SensorCursor, advance_cursor, new_items


def test_new_items_dates_strictly_greater() -> None:
    # 2026-06-30 < position, 2026-07-01 == position (excluded), rest are new.
    assert new_items(
        "2026-07-01",
        ["2026-06-30", "2026-07-02", "2026-07-03"],
    ) == ("2026-07-02", "2026-07-03")


def test_new_items_empty_position_takes_all() -> None:
    # Empty string is the minimum, so every candidate is new.
    assert new_items("", ["a", "b"]) == ("a", "b")


def test_new_items_position_above_all_yields_none() -> None:
    assert new_items("z", ["a", "b"]) == ()


def test_new_items_preserves_input_order_not_sorted() -> None:
    # Order follows the candidate sequence, not sorted order.
    assert new_items("a", ["c", "b", "d"]) == ("c", "b", "d")


def test_new_items_excludes_equal_token() -> None:
    # A candidate equal to the position is not new (idempotency).
    assert new_items("m", ["m"]) == ()


def test_advance_cursor_moves_position_to_max() -> None:
    result = advance_cursor(
        SensorCursor("s", "2026-07-01", 0),
        ["2026-07-02", "2026-07-03"],
    )
    assert result.position == "2026-07-03"


def test_advance_cursor_increments_seen_count() -> None:
    result = advance_cursor(
        SensorCursor("s", "2026-07-01", 0),
        ["2026-07-02", "2026-07-03"],
    )
    assert result.seen_count == 2


def test_advance_cursor_no_new_leaves_position() -> None:
    # All candidates <= position: nothing new, cursor unchanged.
    result = advance_cursor(SensorCursor("s", "z", 4), ["a"])
    assert result.position == "z"


def test_advance_cursor_no_new_leaves_seen_count() -> None:
    result = advance_cursor(SensorCursor("s", "z", 4), ["a"])
    assert result.seen_count == 4


def test_advance_cursor_no_new_returns_same_object() -> None:
    # Idempotent re-poll returns the very same frozen cursor.
    cursor = SensorCursor("s", "z", 4)
    assert advance_cursor(cursor, ["a"]) is cursor


def test_advance_cursor_preserves_name() -> None:
    result = advance_cursor(SensorCursor("sensor-42", "a", 1), ["b", "c"])
    assert result.name == "sensor-42"
    assert result.seen_count == 3


def test_advance_cursor_position_never_regresses() -> None:
    # Even if new items are all below a high position, position holds via max().
    # Here position "5" and candidate "7": "7" > "5" lexicographically, so it
    # advances; verify the max() picks the true maximum among old + new.
    result = advance_cursor(SensorCursor("s", "5", 0), ["7", "6"])
    assert result.position == "7"
    assert result.seen_count == 2


def test_cursor_as_dict_shape() -> None:
    assert SensorCursor("s", "x", 2).as_dict() == {
        "name": "s",
        "position": "x",
        "seen_count": 2,
    }


def test_cursor_from_dict_roundtrip() -> None:
    cursor = SensorCursor("s", "x", 2)
    assert SensorCursor.from_dict(cursor.as_dict()) == cursor


def test_cursor_default_seen_count_is_zero() -> None:
    assert SensorCursor("s", "x").seen_count == 0


def test_cursor_is_frozen_hashable() -> None:
    # Frozen dataclass is hashable and usable in sets.
    assert len({SensorCursor("s", "x", 1), SensorCursor("s", "x", 1)}) == 1

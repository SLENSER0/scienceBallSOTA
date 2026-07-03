"""Incremental-sync cursor tests (§20.4/§20.5/§20.11)."""

from __future__ import annotations

import pytest

from kg_common.sync_cursor import SyncCursor, advance, is_newer, merge_cursors


def test_is_newer_after_cursor() -> None:
    # 2026-07-03 is chronologically after 2026-07-01.
    assert is_newer("2026-07-03", "2026-07-01") is True


def test_is_newer_before_cursor() -> None:
    # 2026-06-01 is before the cursor, so it is not newer.
    assert is_newer("2026-06-01", "2026-07-01") is False


def test_is_newer_cold_start() -> None:
    # Empty cursor = cold start: everything is newer.
    assert is_newer("2026-01-01", "") is True


def test_is_newer_equal_is_not_newer() -> None:
    # Strictly greater: an identical timestamp is not "newer".
    assert is_newer("2026-07-01", "2026-07-01") is False


def test_advance_synced_moves_watermark() -> None:
    c = advance(SyncCursor("eln", "2026-01-01", 0, 0), "2026-05-01")
    assert c.last_cursor == "2026-05-01"
    assert c.records_synced == 1
    assert c.records_skipped == 0
    assert c.system == "eln"


def test_advance_skipped_bumps_skip_counter() -> None:
    c = advance(SyncCursor("eln", "2026-01-01", 0, 0), "2026-05-01")
    c2 = advance(c, "2026-06-01", synced=False)
    assert c2.records_skipped == 1
    # Synced counter untouched; watermark still advances on a skip.
    assert c2.records_synced == 1
    assert c2.last_cursor == "2026-06-01"


def test_advance_never_moves_backward() -> None:
    # An older record must not roll the watermark back.
    c = advance(SyncCursor("eln", "2026-05-01", 0, 0), "2026-01-01")
    assert c.last_cursor == "2026-05-01"
    assert c.records_synced == 1


def test_advance_returns_new_frozen_cursor() -> None:
    original = SyncCursor("eln", "2026-01-01", 0, 0)
    advanced = advance(original, "2026-05-01")
    # Immutable: the source cursor is unchanged.
    assert original.records_synced == 0
    assert advanced is not original


def test_merge_same_system_sums_and_maxes() -> None:
    merged = merge_cursors(
        SyncCursor("eln", "2026-03-01", 2, 1),
        SyncCursor("eln", "2026-05-01", 3, 4),
    )
    assert merged.system == "eln"
    assert merged.last_cursor == "2026-05-01"
    assert merged.records_synced == 5
    assert merged.records_skipped == 5


def test_merge_different_systems_raises() -> None:
    with pytest.raises(ValueError):
        merge_cursors(SyncCursor("a", "x", 1, 0), SyncCursor("b", "y", 1, 0))


def test_as_dict_has_four_keys() -> None:
    d = SyncCursor("eln", "2026-05-01", 3, 2).as_dict()
    assert len(d) == 4
    assert d == {
        "system": "eln",
        "last_cursor": "2026-05-01",
        "records_synced": 3,
        "records_skipped": 2,
    }

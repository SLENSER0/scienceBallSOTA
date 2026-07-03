"""Tests for the incremental-sync cursor — тесты курсора синхронизации (§20.4)."""

from __future__ import annotations

from kg_common.sync_cursor_v204 import SyncCursor, advance, filter_new


def _records() -> list[dict]:
    """Three records dated across 2024-01-01/02/03 — три записи (§20.5)."""
    return [
        {"id": "a", "modified_at": "2024-01-01T00:00:00Z"},
        {"id": "b", "modified_at": "2024-01-02T00:00:00Z"},
        {"id": "c", "modified_at": "2024-01-03T00:00:00Z"},
    ]


def _cursor(value: str | None) -> SyncCursor:
    return SyncCursor(
        source_id="eln",
        cursor_field="modified_at",
        cursor_value=value,
        last_synced_at=None,
    )


def test_filter_new_excludes_boundary_and_older() -> None:
    """cursor_value 2024-01-02 keeps only the 2024-01-03 record."""
    result = filter_new(_records(), _cursor("2024-01-02T00:00:00Z"))
    assert [r["id"] for r in result] == ["c"]


def test_filter_new_boundary_record_excluded() -> None:
    """A record equal to the cursor value is strictly excluded."""
    recs = _records()
    result = filter_new(recs, _cursor("2024-01-02T00:00:00Z"))
    assert all(r["modified_at"] != "2024-01-02T00:00:00Z" for r in result)
    assert len(result) == 1


def test_filter_new_none_returns_all() -> None:
    """A None cursor value is a cold start — all 3 records pass."""
    result = filter_new(_records(), _cursor(None))
    assert [r["id"] for r in result] == ["a", "b", "c"]


def test_filter_new_preserves_record_identity() -> None:
    """filter_new returns the original dict objects, not copies."""
    recs = _records()
    result = filter_new(recs, _cursor(None))
    assert result[0] is recs[0]
    assert result[2] is recs[2]


def test_advance_sets_max_cursor_value() -> None:
    """advance over the batch moves cursor_value to the max timestamp."""
    new = advance(_records(), _cursor("2024-01-01T00:00:00Z"), "2024-06-01T12:00:00Z")
    assert new.cursor_value == "2024-01-03T00:00:00Z"
    assert new.last_synced_at == "2024-06-01T12:00:00Z"


def test_advance_empty_keeps_old_value() -> None:
    """advance on an empty batch keeps the old cursor_value, stamps time."""
    old = _cursor("2024-01-02T00:00:00Z")
    new = advance([], old, "2024-06-01T12:00:00Z")
    assert new.cursor_value == "2024-01-02T00:00:00Z"
    assert new.last_synced_at == "2024-06-01T12:00:00Z"


def test_advance_empty_from_none_stays_none() -> None:
    """advance([]) from a cold-start cursor leaves cursor_value None."""
    new = advance([], _cursor(None), "t")
    assert new.cursor_value is None


def test_as_dict_round_trips_source_id() -> None:
    """as_dict exposes source_id and the full watermark state."""
    d = _cursor("2024-01-03T00:00:00Z").as_dict()
    assert d["source_id"] == "eln"
    assert d["cursor_field"] == "modified_at"
    assert d["cursor_value"] == "2024-01-03T00:00:00Z"
    assert d["last_synced_at"] is None


def test_filter_then_advance_pipeline() -> None:
    """End-to-end: filter to new, advance past them — конвейер (§20.5)."""
    cur = _cursor("2024-01-02T00:00:00Z")
    new_recs = filter_new(_records(), cur)
    assert [r["id"] for r in new_recs] == ["c"]
    advanced = advance(new_recs, cur, "2024-06-01T00:00:00Z")
    assert advanced.cursor_value == "2024-01-03T00:00:00Z"
    assert filter_new(_records(), advanced) == []

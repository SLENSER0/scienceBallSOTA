"""Tests for connector sync-metrics counters (§20.13)."""

from __future__ import annotations

import pytest

from kg_common.connector_metrics_sync import (
    ConnectorSyncMetrics,
    merge,
    record,
    total_processed,
)


def test_defaults_are_zero() -> None:
    m = ConnectorSyncMetrics("elabftw")
    assert m.system == "elabftw"
    assert m.records_synced == 0
    assert m.records_skipped == 0
    assert m.merge_auto == 0
    assert m.merge_review == 0
    assert m.errors == 0


def test_record_adds_single_field() -> None:
    m = ConnectorSyncMetrics("elabftw")
    assert record(m, synced=2).records_synced == 2


def test_record_accumulates() -> None:
    m = ConnectorSyncMetrics("elabftw")
    assert record(record(m, synced=1), synced=1).records_synced == 2


def test_record_errors() -> None:
    m = ConnectorSyncMetrics("elabftw")
    assert record(m, errors=1).errors == 1


def test_record_all_fields_at_once() -> None:
    m = ConnectorSyncMetrics("x")
    out = record(m, synced=1, skipped=2, merge_auto=3, merge_review=4, errors=5)
    assert out.as_dict() == {
        "system": "x",
        "records_synced": 1,
        "records_skipped": 2,
        "merge_auto": 3,
        "merge_review": 4,
        "errors": 5,
    }


def test_original_is_immutable() -> None:
    m = ConnectorSyncMetrics("x")
    record(m, synced=5)
    assert m.records_synced == 0


def test_merge_sums_counters() -> None:
    a = ConnectorSyncMetrics("x", merge_auto=1)
    b = ConnectorSyncMetrics("x", merge_auto=2)
    assert merge(a, b).merge_auto == 3


def test_merge_sums_every_field() -> None:
    a = ConnectorSyncMetrics("x", 1, 2, 3, 4, 5)
    b = ConnectorSyncMetrics("x", 10, 20, 30, 40, 50)
    out = merge(a, b)
    assert out.as_dict() == {
        "system": "x",
        "records_synced": 11,
        "records_skipped": 22,
        "merge_auto": 33,
        "merge_review": 44,
        "errors": 55,
    }


def test_merge_mismatched_system_raises() -> None:
    with pytest.raises(ValueError):
        merge(ConnectorSyncMetrics("x"), ConnectorSyncMetrics("y"))


def test_total_processed() -> None:
    m = ConnectorSyncMetrics("x", records_synced=3, records_skipped=2)
    assert total_processed(m) == 5


def test_total_processed_ignores_other_counters() -> None:
    m = ConnectorSyncMetrics("x", records_synced=3, records_skipped=2, errors=9)
    assert total_processed(m) == 5


def test_as_dict_has_six_keys() -> None:
    keys = set(ConnectorSyncMetrics("x").as_dict())
    assert keys == {
        "system",
        "records_synced",
        "records_skipped",
        "merge_auto",
        "merge_review",
        "errors",
    }


def test_frozen_cannot_mutate() -> None:
    from dataclasses import FrozenInstanceError

    m = ConnectorSyncMetrics("x")
    with pytest.raises(FrozenInstanceError):
        m.records_synced = 99  # type: ignore[misc]

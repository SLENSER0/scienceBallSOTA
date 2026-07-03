"""Tests for :mod:`kg_common.connector_metrics` — метрики коннекторов (§20.13)."""

from __future__ import annotations

from kg_common.connector_metrics import (
    ConnectorMetrics,
    aggregate,
    combine,
    success_rate,
)


def test_defaults_all_zero() -> None:
    m = ConnectorMetrics()
    assert m.records_synced == 0
    assert m.records_skipped == 0
    assert m.merge_auto == 0
    assert m.merge_review == 0
    assert m.errors == 0


def test_combine_sums_records_synced() -> None:
    combined = combine(
        ConnectorMetrics(records_synced=2),
        ConnectorMetrics(records_synced=3),
    )
    assert combined.records_synced == 5


def test_combine_preserves_merge_auto_and_review_sums() -> None:
    combined = combine(
        ConnectorMetrics(merge_auto=4, merge_review=1),
        ConnectorMetrics(merge_auto=6, merge_review=9),
    )
    assert combined.merge_auto == 10
    assert combined.merge_review == 10


def test_combine_sums_every_field() -> None:
    combined = combine(
        ConnectorMetrics(
            records_synced=1, records_skipped=2, merge_auto=3, merge_review=4, errors=5
        ),
        ConnectorMetrics(
            records_synced=10, records_skipped=20, merge_auto=30, merge_review=40, errors=50
        ),
    )
    assert combined.as_dict() == {
        "records_synced": 11,
        "records_skipped": 22,
        "merge_auto": 33,
        "merge_review": 44,
        "errors": 55,
    }


def test_combine_does_not_mutate_inputs() -> None:
    a = ConnectorMetrics(records_synced=2)
    b = ConnectorMetrics(records_synced=3)
    combine(a, b)
    assert a.records_synced == 2
    assert b.records_synced == 3


def test_aggregate_sums_errors_across_three() -> None:
    result = aggregate(
        [
            ConnectorMetrics(errors=1),
            ConnectorMetrics(errors=2),
            ConnectorMetrics(errors=3),
        ]
    )
    assert result.errors == 6


def test_aggregate_empty_is_all_zeros() -> None:
    assert aggregate([]) == ConnectorMetrics()


def test_aggregate_single_returns_equal_value() -> None:
    m = ConnectorMetrics(records_synced=7, errors=2)
    assert aggregate([m]) == m


def test_aggregate_folds_all_fields() -> None:
    result = aggregate(
        [
            ConnectorMetrics(
                records_synced=1, records_skipped=1, merge_auto=1, merge_review=1, errors=1
            ),
            ConnectorMetrics(
                records_synced=2, records_skipped=2, merge_auto=2, merge_review=2, errors=2
            ),
            ConnectorMetrics(
                records_synced=3, records_skipped=3, merge_auto=3, merge_review=3, errors=3
            ),
        ]
    )
    assert result.as_dict() == {
        "records_synced": 6,
        "records_skipped": 6,
        "merge_auto": 6,
        "merge_review": 6,
        "errors": 6,
    }


def test_success_rate_nine_of_ten() -> None:
    assert success_rate(ConnectorMetrics(records_synced=9, errors=1)) == 0.9


def test_success_rate_zero_denominator_is_zero() -> None:
    assert success_rate(ConnectorMetrics()) == 0.0


def test_success_rate_all_synced_is_one() -> None:
    assert success_rate(ConnectorMetrics(records_synced=5, errors=0)) == 1.0


def test_success_rate_ignores_skipped_and_merges() -> None:
    m = ConnectorMetrics(
        records_synced=3, records_skipped=100, merge_auto=50, merge_review=50, errors=1
    )
    assert success_rate(m) == 0.75


def test_as_dict_has_exactly_five_keys() -> None:
    keys = ConnectorMetrics().as_dict().keys()
    assert len(keys) == 5
    assert set(keys) == {
        "records_synced",
        "records_skipped",
        "merge_auto",
        "merge_review",
        "errors",
    }


def test_frozen_is_immutable() -> None:
    import dataclasses

    m = ConnectorMetrics()
    try:
        m.errors = 9  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover
        raise AssertionError("ConnectorMetrics must be frozen")

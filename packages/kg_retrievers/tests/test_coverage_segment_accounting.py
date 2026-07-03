"""Tests for coverage-denominator reconciliation (§25.5).

RU: Ручные проверки сверки знаменателя покрытия.
EN: Hand-checkable tests for coverage-denominator reconciliation.
"""

from __future__ import annotations

from kg_retrievers.coverage_segment_accounting import (
    AccountingReport,
    AccountingRow,
    reconcile_coverage,
)


def _row(context_key: str, total: int, seen: int, emitted: int) -> dict[str, object]:
    """RU: Собрать входную строку. EN: Build one input row dict."""
    return {
        "context_key": context_key,
        "total_segments": total,
        "seen_segments": seen,
        "emitted_facts": emitted,
    }


def test_clean_row_unlogged_and_ratio() -> None:
    """total=10, seen=7, emitted=3 -> unlogged 3, ratio 0.7, no anomaly."""
    report = reconcile_coverage([_row("ctx", 10, 7, 3)])
    (row,) = report.rows
    assert row.unlogged == 3
    assert row.coverage_ratio == 0.7
    assert row.anomaly == ""


def test_seen_exceeds_total_anomaly() -> None:
    """seen(8) > total(5) -> anomaly seen_exceeds_total, unlogged clamped to 0."""
    report = reconcile_coverage([_row("ctx", 5, 8, 0)])
    (row,) = report.rows
    assert row.anomaly == "seen_exceeds_total"
    assert row.unlogged == 0


def test_emitted_exceeds_seen_anomaly() -> None:
    """total=10, seen=4, emitted=6 -> anomaly emitted_exceeds_seen."""
    report = reconcile_coverage([_row("ctx", 10, 4, 6)])
    (row,) = report.rows
    assert row.anomaly == "emitted_exceeds_seen"


def test_total_unlogged_sums_across_rows() -> None:
    """total_unlogged is the sum of per-row unlogged values."""
    report = reconcile_coverage(
        [
            _row("a", 10, 7, 3),  # unlogged 3
            _row("b", 4, 1, 0),  # unlogged 3
            _row("c", 5, 5, 2),  # unlogged 0
        ]
    )
    assert report.total_unlogged == 6


def test_n_anomalies_counts_non_empty() -> None:
    """n_anomalies counts rows with a non-empty anomaly code."""
    report = reconcile_coverage(
        [
            _row("clean", 10, 7, 3),  # ""
            _row("over", 5, 8, 0),  # seen_exceeds_total
            _row("emit", 10, 4, 6),  # emitted_exceeds_seen
        ]
    )
    assert report.n_anomalies == 2


def test_zero_total_no_division_error() -> None:
    """total=0 gives coverage_ratio 0.0 without a ZeroDivisionError."""
    report = reconcile_coverage([_row("ctx", 0, 0, 0)])
    (row,) = report.rows
    assert row.coverage_ratio == 0.0
    assert row.unlogged == 0
    assert row.anomaly == ""


def test_fully_logged_row_unlogged_zero() -> None:
    """seen == total -> unlogged 0 and full coverage ratio."""
    report = reconcile_coverage([_row("ctx", 6, 6, 2)])
    (row,) = report.rows
    assert row.unlogged == 0
    assert row.coverage_ratio == 1.0
    assert row.anomaly == ""


def test_empty_input_gives_zero_totals() -> None:
    """No rows -> empty report with zero aggregates."""
    report = reconcile_coverage([])
    assert report.rows == []
    assert report.total_unlogged == 0
    assert report.n_anomalies == 0


def test_as_dict_roundtrip() -> None:
    """as_dict exposes all row and report fields."""
    report = reconcile_coverage([_row("ctx", 10, 7, 3)])
    assert isinstance(report, AccountingReport)
    d = report.as_dict()
    assert d["total_unlogged"] == 3
    assert d["n_anomalies"] == 0
    (row_dict,) = d["rows"]
    assert row_dict == {
        "context_key": "ctx",
        "total": 10,
        "seen": 7,
        "emitted": 3,
        "unlogged": 3,
        "coverage_ratio": 0.7,
        "anomaly": "",
    }


def test_row_is_frozen() -> None:
    """AccountingRow is an immutable frozen dataclass."""
    report = reconcile_coverage([_row("ctx", 10, 7, 3)])
    (row,) = report.rows
    assert isinstance(row, AccountingRow)
    try:
        row.total = 99  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("AccountingRow should be frozen")

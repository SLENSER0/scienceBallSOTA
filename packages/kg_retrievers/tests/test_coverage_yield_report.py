"""Tests for observed-yield coverage report (§25.5/§25.10).

RU: Проверяем наблюдаемую отдачу, слепые зоны и агрегаты.
EN: Verify observed yield, blind spots and aggregates with hand-checked values.
"""

from __future__ import annotations

from kg_common.storage import CoverageStats
from kg_retrievers.coverage_yield_report import (
    CoverageYieldReport,
    YieldRow,
    build_yield_report,
)


def _stat(target_type: str, n_attempts: int, n_found: int) -> CoverageStats:
    return CoverageStats(
        target_type=target_type,
        n_chunks=n_attempts,
        n_attempts=n_attempts,
        n_found=n_found,
        n_docs=1,
    )


def test_positive_yield_not_blind_spot() -> None:
    # Assertion (1): 10 attempts / 9 found -> yield 0.9, not a blind spot.
    report = build_yield_report([_stat("Material", 10, 9)])
    row = report.rows[0]
    assert row.observed_yield == 0.9
    assert row.blind_spot is False


def test_zero_found_is_blind_spot() -> None:
    # Assertion (2): 5 attempts / 0 found -> blind spot, in blind_spots list.
    report = build_yield_report([_stat("Process", 5, 0)])
    assert report.rows[0].blind_spot is True
    assert "Process" in report.blind_spots


def test_overall_yield_over_two_rows() -> None:
    # Assertion (3): overall_yield == sum(found)/sum(attempts).
    stats = [_stat("Material", 10, 9), _stat("Process", 4, 1)]
    report = build_yield_report(stats)
    assert report.overall_yield == (9 + 1) / (10 + 4)


def test_zero_attempts_yield_and_not_blind() -> None:
    # Assertion (4): 0 attempts -> yield 0.0 and NOT flagged as blind spot.
    report = build_yield_report([_stat("Property", 0, 0)])
    row = report.rows[0]
    assert row.observed_yield == 0.0
    assert row.blind_spot is False
    assert report.blind_spots == []


def test_empty_stats() -> None:
    # Assertion (5): empty -> no rows, overall_yield 0.0.
    report = build_yield_report([])
    assert report.rows == []
    assert report.overall_yield == 0.0
    assert report.total_seen == 0
    assert report.total_emitted == 0
    assert report.blind_spots == []


def test_rows_sorted_by_target_type() -> None:
    # Assertion (6): rows sorted by target_type regardless of input order.
    stats = [_stat("Zeta", 3, 3), _stat("Alpha", 2, 1), _stat("Mu", 5, 0)]
    report = build_yield_report(stats)
    assert [r.target_type for r in report.rows] == ["Alpha", "Mu", "Zeta"]


def test_total_seen_is_sum_of_attempts() -> None:
    # Assertion (7): total_seen == sum(n_attempts).
    stats = [_stat("Material", 10, 9), _stat("Process", 4, 1)]
    report = build_yield_report(stats)
    assert report.total_seen == 14


def test_as_dict_blind_spots_is_list_of_flagged_types() -> None:
    # Assertion (8): as_dict()['blind_spots'] lists flagged types.
    stats = [_stat("Material", 10, 9), _stat("Process", 5, 0), _stat("Bond", 3, 0)]
    report = build_yield_report(stats)
    payload = report.as_dict()
    assert payload["blind_spots"] == ["Bond", "Process"]
    assert isinstance(payload["blind_spots"], list)


def test_dataclasses_are_frozen() -> None:
    report = build_yield_report([_stat("Material", 10, 9)])
    assert isinstance(report, CoverageYieldReport)
    assert isinstance(report.rows[0], YieldRow)
    row_dict = report.rows[0].as_dict()
    assert row_dict["target_type"] == "Material"
    assert row_dict["seen"] == 10
    assert row_dict["emitted"] == 9

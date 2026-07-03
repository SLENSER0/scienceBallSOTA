"""Tests for coverage burndown projection (§25.5)."""

from __future__ import annotations

from kg_retrievers.coverage_burndown import BurndownReport, coverage_burndown


def _snaps(opens: list[int]) -> list[dict]:
    """Build snapshot dicts from a list of open-cell counts."""
    return [{"open_cells": value} for value in opens]


def test_decreasing_series_projects_eta() -> None:
    report = coverage_burndown(_snaps([100, 80, 60]))
    assert report.total_closed == 40
    assert report.avg_close_rate == 20.0
    assert report.remaining == 60
    assert report.eta_runs == 3.0


def test_increasing_series_negative_rate_no_eta() -> None:
    report = coverage_burndown(_snaps([50, 70]))
    assert report.total_closed == -20
    assert report.avg_close_rate < 0
    assert report.eta_runs is None
    assert report.remaining == 70


def test_single_snapshot_flat_rate_no_eta() -> None:
    report = coverage_burndown(_snaps([42]))
    assert report.avg_close_rate == 0.0
    assert report.eta_runs is None
    assert report.remaining == 42


def test_empty_series() -> None:
    report = coverage_burndown(_snaps([]))
    assert report.avg_close_rate == 0.0
    assert report.eta_runs is None
    assert report.remaining == 0
    assert report.points == ()


def test_flat_series_no_eta() -> None:
    report = coverage_burndown(_snaps([40, 40, 40]))
    assert report.total_closed == 0
    assert report.avg_close_rate == 0.0
    assert report.eta_runs is None


def test_points_length_matches_snapshots() -> None:
    snaps = _snaps([100, 80, 60])
    report = coverage_burndown(snaps)
    assert len(report.points) == len(snaps)
    assert [point["open"] for point in report.points] == [100, 80, 60]


def test_remaining_equals_last_open() -> None:
    report = coverage_burndown(_snaps([90, 55, 33, 12]))
    assert report.remaining == 12


def test_custom_open_key() -> None:
    snaps = [{"remaining_gaps": 30}, {"remaining_gaps": 10}]
    report = coverage_burndown(snaps, open_key="remaining_gaps")
    assert report.total_closed == 20
    assert report.avg_close_rate == 20.0
    assert report.eta_runs == 0.5


def test_as_dict_shape() -> None:
    report = coverage_burndown(_snaps([100, 80, 60]))
    payload = report.as_dict()
    assert isinstance(payload, dict)
    assert isinstance(payload["points"], list)
    assert payload["total_closed"] == 40
    assert payload["eta_runs"] == 3.0
    assert isinstance(report, BurndownReport)

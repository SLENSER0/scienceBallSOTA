"""Tests for per-report freshness / staleness (§11.10).

Hand-checkable freshness assertions; pure data logic, no store needed.
Ручная проверка устаревания отчётов сообществ относительно источников.
"""

from __future__ import annotations

from kg_retrievers.community_report_freshness import (
    Freshness,
    assess_freshness,
    stale_reports,
)


def _report(community_id: int, built_at: float, doc_ids: list[str]) -> dict:
    return {"community_id": community_id, "built_at": built_at, "doc_ids": doc_ids}


def test_doc_updated_after_built_is_stale_with_positive_lag() -> None:
    report = _report(1, built_at=100.0, doc_ids=["d1"])
    fresh = assess_freshness(report, {"d1": 150.0})
    assert fresh.stale is True
    assert fresh.newest_source_ts == 150.0
    assert fresh.report_ts == 100.0
    assert fresh.lag_seconds == 50.0


def test_doc_older_than_built_is_fresh_with_zero_lag() -> None:
    report = _report(2, built_at=200.0, doc_ids=["d1"])
    fresh = assess_freshness(report, {"d1": 120.0})
    assert fresh.stale is False
    assert fresh.newest_source_ts == 120.0
    assert fresh.lag_seconds == 0.0


def test_absent_doc_id_is_ignored() -> None:
    report = _report(3, built_at=100.0, doc_ids=["d1", "missing"])
    fresh = assess_freshness(report, {"d1": 90.0})
    # only d1 is known; "missing" contributes nothing
    assert fresh.newest_source_ts == 90.0
    assert fresh.stale is False
    assert fresh.lag_seconds == 0.0


def test_report_with_no_doc_ids_is_fresh() -> None:
    report = _report(4, built_at=100.0, doc_ids=[])
    fresh = assess_freshness(report, {"d1": 999.0})
    assert fresh.newest_source_ts == 0.0
    assert fresh.stale is False
    assert fresh.lag_seconds == 0.0


def test_all_doc_ids_absent_from_map_is_fresh() -> None:
    report = _report(5, built_at=100.0, doc_ids=["x", "y"])
    fresh = assess_freshness(report, {})
    assert fresh.newest_source_ts == 0.0
    assert fresh.stale is False


def test_equal_timestamps_are_not_stale() -> None:
    report = _report(6, built_at=100.0, doc_ids=["d1"])
    fresh = assess_freshness(report, {"d1": 100.0})
    assert fresh.stale is False
    assert fresh.lag_seconds == 0.0
    assert fresh.newest_source_ts == 100.0


def test_two_docs_newest_source_is_the_max() -> None:
    report = _report(7, built_at=100.0, doc_ids=["d1", "d2"])
    fresh = assess_freshness(report, {"d1": 130.0, "d2": 170.0})
    assert fresh.newest_source_ts == 170.0
    assert fresh.stale is True
    assert fresh.lag_seconds == 70.0


def test_stale_reports_returns_sorted_ids() -> None:
    doc_updated_at = {"d1": 150.0, "d2": 50.0, "d3": 300.0}
    reports = [
        _report(9, built_at=100.0, doc_ids=["d1"]),  # stale (150 > 100)
        _report(3, built_at=100.0, doc_ids=["d2"]),  # fresh (50 < 100)
        _report(7, built_at=100.0, doc_ids=["d3"]),  # stale (300 > 100)
        _report(1, built_at=100.0, doc_ids=[]),  # fresh (no docs)
    ]
    assert stale_reports(reports, doc_updated_at) == [7, 9]


def test_stale_reports_empty_when_all_fresh() -> None:
    reports = [_report(1, built_at=500.0, doc_ids=["d1"])]
    assert stale_reports(reports, {"d1": 10.0}) == []


def test_as_dict_exposes_all_five_fields() -> None:
    fresh = Freshness(
        community_id=1,
        stale=True,
        newest_source_ts=150.0,
        report_ts=100.0,
        lag_seconds=50.0,
    )
    d = fresh.as_dict()
    assert d == {
        "community_id": 1,
        "stale": True,
        "newest_source_ts": 150.0,
        "report_ts": 100.0,
        "lag_seconds": 50.0,
    }
    assert set(d.keys()) == {
        "community_id",
        "stale",
        "newest_source_ts",
        "report_ts",
        "lag_seconds",
    }


def test_frozen_dataclass_is_immutable() -> None:
    fresh = assess_freshness(_report(1, 100.0, ["d1"]), {"d1": 200.0})
    try:
        fresh.stale = False  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("Freshness must be frozen/immutable")

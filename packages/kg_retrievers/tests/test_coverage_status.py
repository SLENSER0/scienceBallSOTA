"""Tests for the coverage-cell status classifier (§24.15).

Hand-checkable cases exercising each rule and the inclusive staleness boundary.
"""

from __future__ import annotations

from kg_retrievers.coverage_status import (
    ABSENT,
    COVERED,
    STALE,
    THIN,
    VERIFIED,
    CoverageStatus,
    classify_cell,
)

CURRENT_YEAR = 2026


def test_zero_evidence_is_absent() -> None:
    result = classify_cell(0, 0, None, 0.0, current_year=CURRENT_YEAR)
    assert result.status == ABSENT
    assert result.is_stale is False


def test_old_latest_year_is_stale() -> None:
    # 2019 vs current 2026 with stale_years 5: boundary is 2021, 2019 < 2021.
    result = classify_cell(3, 1, 2019, 0.9, current_year=CURRENT_YEAR, stale_years=5)
    assert result.status == STALE
    assert result.is_stale is True


def test_verified_when_verified_and_confident_recent() -> None:
    result = classify_cell(3, 2, 2025, 0.9, current_year=CURRENT_YEAR)
    assert result.status == VERIFIED
    assert result.is_stale is False


def test_thin_when_single_unverified_recent() -> None:
    result = classify_cell(1, 0, 2025, 0.5, current_year=CURRENT_YEAR)
    assert result.status == THIN
    assert result.is_stale is False


def test_covered_when_several_unverified_recent() -> None:
    result = classify_cell(4, 0, 2025, 0.5, current_year=CURRENT_YEAR)
    assert result.status == COVERED
    assert result.is_stale is False


def test_confidence_carried_through_unchanged() -> None:
    result = classify_cell(4, 0, 2025, 0.42, current_year=CURRENT_YEAR)
    assert result.confidence == 0.42


def test_stale_boundary_is_inclusive_not_stale() -> None:
    # latest_year == current - stale_years (2021) is exactly at the boundary.
    result = classify_cell(3, 0, 2021, 0.5, current_year=CURRENT_YEAR, stale_years=5)
    assert result.status != STALE
    assert result.is_stale is False


def test_is_stale_false_for_recent_covered_cell() -> None:
    result = classify_cell(4, 0, 2026, 0.5, current_year=CURRENT_YEAR)
    assert result.is_stale is False
    assert result.status == COVERED


def test_absent_takes_priority_over_staleness() -> None:
    # Even with an ancient year, zero evidence classifies as absent (not stale).
    result = classify_cell(0, 0, 1990, 0.9, current_year=CURRENT_YEAR)
    assert result.status == ABSENT
    assert result.is_stale is False


def test_stale_takes_priority_over_verified() -> None:
    # Verified + confident, but too old → stale wins.
    result = classify_cell(5, 3, 2010, 0.95, current_year=CURRENT_YEAR)
    assert result.status == STALE
    assert result.is_stale is True


def test_verified_needs_confidence_floor() -> None:
    # Verified count > 0 but confidence below the floor falls through to covered.
    result = classify_cell(4, 2, 2025, 0.5, current_year=CURRENT_YEAR, verified_conf=0.7)
    assert result.status == COVERED


def test_confidence_exactly_at_verified_floor() -> None:
    result = classify_cell(3, 1, 2025, 0.7, current_year=CURRENT_YEAR, verified_conf=0.7)
    assert result.status == VERIFIED


def test_none_latest_year_is_never_stale() -> None:
    result = classify_cell(2, 0, None, 0.5, current_year=CURRENT_YEAR)
    assert result.is_stale is False
    assert result.status == COVERED


def test_as_dict_roundtrip() -> None:
    result = classify_cell(3, 2, 2025, 0.9, current_year=CURRENT_YEAR)
    d = result.as_dict()
    assert d["status"] == VERIFIED
    assert d["evidence_count"] == 3
    assert d["verified_count"] == 2
    assert d["is_stale"] is False
    assert d["confidence"] == 0.9
    assert "schema_version" in d


def test_frozen_dataclass_is_immutable() -> None:
    result = CoverageStatus(VERIFIED, 3, 2, False, 0.9)
    try:
        result.status = ABSENT  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("CoverageStatus should be frozen")

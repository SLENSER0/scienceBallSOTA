"""Tests for raw seen/emitted coverage aggregation by modality (§25.5)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_common.storage.base import CoverageStats
from kg_retrievers.coverage_report import (
    CoverageReport,
    ModalityCoverage,
    aggregate_coverage,
)


def _stats(target_type: str, n_attempts: int, n_found: int) -> CoverageStats:
    return CoverageStats(
        target_type=target_type,
        n_chunks=n_attempts,
        n_attempts=n_attempts,
        n_found=n_found,
        n_docs=1,
    )


def test_yield_and_blind_spot() -> None:
    report = aggregate_coverage([_stats("table_row", 10, 9), _stats("prose", 20, 0)])
    assert report.by_modality["table_row"].observed_yield == 0.9
    assert report.by_modality["table_row"].seen_segments == 10
    assert report.by_modality["table_row"].emitted_facts == 9
    # Prose is an honest blind spot: seen 20, emitted 0 — not dropped.
    assert report.by_modality["prose"].observed_yield == 0.0
    assert report.by_modality["prose"].seen_segments == 20
    assert report.by_modality["prose"].emitted_facts == 0
    assert report.total_seen == 30
    assert report.total_emitted == 9
    assert report.overall_yield == 0.3


def test_same_modality_rows_are_summed() -> None:
    report = aggregate_coverage([_stats("table_row", 10, 4), _stats("table_row", 30, 8)])
    row = report.by_modality["table_row"]
    assert row.seen_segments == 40
    assert row.emitted_facts == 12
    assert row.observed_yield == 12 / 40
    assert report.total_seen == 40
    assert report.total_emitted == 12
    assert report.overall_yield == 0.3
    assert list(report.by_modality) == ["table_row"]


def test_empty_input_no_divide_by_zero() -> None:
    report = aggregate_coverage([])
    assert report.by_modality == {}
    assert report.total_seen == 0
    assert report.total_emitted == 0
    assert report.overall_yield == 0.0


def test_accepts_equivalent_dicts() -> None:
    report = aggregate_coverage(
        [
            {"target_type": "catalog_row", "n_attempts": 5, "n_found": 5},
            {"target_type": "catalog_row", "n_attempts": 5, "n_found": 0},
        ]
    )
    row = report.by_modality["catalog_row"]
    assert row.seen_segments == 10
    assert row.emitted_facts == 5
    assert row.observed_yield == 0.5
    assert report.overall_yield == 0.5


def test_mixed_dict_and_stats_objects() -> None:
    report = aggregate_coverage(
        [
            _stats("prose", 4, 1),
            {"target_type": "prose", "n_attempts": 6, "n_found": 2},
            _stats("table_row", 10, 10),
        ]
    )
    prose = report.by_modality["prose"]
    assert prose.seen_segments == 10
    assert prose.emitted_facts == 3
    assert prose.observed_yield == 0.3
    assert report.by_modality["table_row"].observed_yield == 1.0
    assert report.total_seen == 20
    assert report.total_emitted == 13
    assert report.overall_yield == 13 / 20


def test_frozen_and_as_dict_shapes() -> None:
    report = aggregate_coverage([_stats("table_row", 2, 1)])
    assert isinstance(report, CoverageReport)
    row = report.by_modality["table_row"]
    assert isinstance(row, ModalityCoverage)
    assert row.as_dict() == {
        "modality": "table_row",
        "seen_segments": 2,
        "emitted_facts": 1,
        "observed_yield": 0.5,
    }
    assert report.as_dict() == {
        "by_modality": {
            "table_row": {
                "modality": "table_row",
                "seen_segments": 2,
                "emitted_facts": 1,
                "observed_yield": 0.5,
            }
        },
        "total_seen": 2,
        "total_emitted": 1,
        "overall_yield": 0.5,
    }


def test_dataclasses_are_frozen() -> None:
    row = ModalityCoverage("prose", 1, 0, 0.0)
    with pytest.raises(FrozenInstanceError):
        row.seen_segments = 5  # type: ignore[misc]

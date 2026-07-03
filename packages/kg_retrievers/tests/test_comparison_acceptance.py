"""Tests for the comparison-table acceptance audit (§24.13)."""

from __future__ import annotations

from kg_retrievers.comparison_acceptance import AcceptanceReport, audit_comparison


def test_all_gap_table_passes_with_gap_cells_equal_total() -> None:
    table = {
        "throughput": {"kuzu": {"gap": True}, "neo4j": {"gap": True}},
        "license": {"kuzu": {"gap": True}, "neo4j": {"gap": True}},
    }
    report = audit_comparison(table)
    assert report.passed is True
    assert report.total_cells == 4
    assert report.gap_cells == report.total_cells == 4
    assert report.evidence_cells == 0
    assert report.invalid_cells == ()


def test_evidence_ids_counts_as_evidence_cell() -> None:
    table = {"latency": {"kuzu": {"evidence_ids": ["e1"]}}}
    report = audit_comparison(table)
    assert report.passed is True
    assert report.evidence_cells == 1
    assert report.gap_cells == 0
    assert report.total_cells == 1


def test_empty_cell_is_invalid_and_fails() -> None:
    table = {"latency": {"kuzu": {}}}
    report = audit_comparison(table)
    assert report.passed is False
    assert report.invalid_cells == (("latency", "kuzu"),)
    assert report.evidence_cells == 0
    assert report.gap_cells == 0


def test_bare_value_without_evidence_or_gap_is_invalid() -> None:
    table = {"latency": {"kuzu": {"value": 5}}}
    report = audit_comparison(table)
    assert report.passed is False
    assert report.invalid_cells == (("latency", "kuzu"),)


def test_empty_evidence_list_is_invalid() -> None:
    table = {"latency": {"kuzu": {"evidence_ids": []}}}
    report = audit_comparison(table)
    assert report.passed is False
    assert report.invalid_cells == (("latency", "kuzu"),)
    assert report.evidence_cells == 0


def test_mixed_table_totals_add_up() -> None:
    table = {
        "throughput": {
            "kuzu": {"evidence_ids": ["e1"]},
            "neo4j": {"gap": True},
        },
        "license": {
            "kuzu": {"value": 5},
            "neo4j": {"evidence_ids": []},
        },
    }
    report = audit_comparison(table)
    assert report.total_cells == 4
    assert report.evidence_cells == 1
    assert report.gap_cells == 1
    assert len(report.invalid_cells) == 2
    assert report.evidence_cells + report.gap_cells + len(report.invalid_cells) == (
        report.total_cells
    )
    assert report.passed is False


def test_invalid_cells_lists_exact_row_col_pairs() -> None:
    table = {
        "throughput": {"kuzu": {}, "neo4j": {"evidence_ids": ["e2"]}},
        "license": {"kuzu": {"value": 1}},
    }
    report = audit_comparison(table)
    assert set(report.invalid_cells) == {("throughput", "kuzu"), ("license", "kuzu")}


def test_evidence_takes_precedence_when_both_present() -> None:
    table = {"latency": {"kuzu": {"evidence_ids": ["e1"], "gap": True}}}
    report = audit_comparison(table)
    assert report.evidence_cells == 1
    assert report.gap_cells == 0
    assert report.evidence_cells + report.gap_cells == report.total_cells == 1


def test_empty_table_passes_with_zero_cells() -> None:
    report = audit_comparison({})
    assert report.passed is True
    assert report.total_cells == 0
    assert report.evidence_cells == 0
    assert report.gap_cells == 0
    assert report.invalid_cells == ()


def test_report_is_frozen_and_as_dict_round_trips() -> None:
    report = AcceptanceReport(
        passed=False,
        total_cells=2,
        evidence_cells=1,
        gap_cells=0,
        invalid_cells=(("row", "col"),),
    )
    data = report.as_dict()
    assert data == {
        "passed": False,
        "total_cells": 2,
        "evidence_cells": 1,
        "gap_cells": 0,
        "invalid_cells": [["row", "col"]],
    }

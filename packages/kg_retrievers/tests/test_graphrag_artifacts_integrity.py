"""Tests for GraphRAG artifacts integrity (§11.4)."""

from __future__ import annotations

import copy

from kg_retrievers.graphrag_artifacts_integrity import (
    REPORT_COLUMNS,
    REQUIRED_TABLES,
    IntegrityReport,
    check_artifacts,
)


def _report_row(cid: str, level: int) -> dict:
    """A complete community_reports row carrying every REPORT_COLUMN."""
    return {
        "community_id": cid,
        "title": f"Community {cid}",
        "summary": f"Summary of community {cid}.",
        "level": level,
        "rank": 1.0,
        "findings": [{"explanation": "finding"}],
    }


def _fixture() -> dict[str, list[dict]]:
    """A complete two-level artifact set: 2 communities at levels 0 and 1."""
    return {
        "entities": [{"id": "e1", "name": "Iron"}, {"id": "e2", "name": "Steel"}],
        "relationships": [{"source": "e1", "target": "e2", "weight": 1.0}],
        "text_units": [{"id": "t1", "text": "Iron and steel."}],
        "communities": [{"id": "c0", "level": 0}, {"id": "c1", "level": 1}],
        "community_reports": [_report_row("c0", 0), _report_row("c1", 1)],
    }


def test_complete_two_level_fixture_ok() -> None:
    report = check_artifacts(_fixture())
    assert isinstance(report, IntegrityReport)
    assert report.ok is True
    assert report.errors == []
    assert report.n_communities == 2
    assert report.n_reports == 2
    assert report.max_level == 1


def test_missing_community_reports_table() -> None:
    tables = _fixture()
    del tables["community_reports"]
    report = check_artifacts(tables)
    assert report.ok is False
    assert "missing table: community_reports" in report.errors
    # n_reports falls to 0 with the reports table gone.
    assert report.n_reports == 0


def test_report_row_missing_findings() -> None:
    tables = _fixture()
    del tables["community_reports"][1]["findings"]
    report = check_artifacts(tables)
    assert report.ok is False
    assert "community_reports row 1: missing column: findings" in report.errors


def test_zero_communities() -> None:
    tables = _fixture()
    tables["communities"] = []
    report = check_artifacts(tables)
    assert report.ok is False
    assert report.n_communities == 0
    assert "no communities: n_communities must be > 0" in report.errors


def test_empty_summary_lowers_n_reports_and_errors() -> None:
    tables = _fixture()
    tables["community_reports"][1]["summary"] = "   "
    report = check_artifacts(tables)
    assert report.ok is False
    assert report.n_reports == 1
    assert report.n_reports < report.n_communities
    assert "community_reports row 1: empty summary" in report.errors


def test_as_dict_errors_is_list() -> None:
    report = check_artifacts(_fixture())
    d = report.as_dict()
    assert isinstance(d["errors"], list)
    assert d["ok"] is True
    assert d["n_communities"] == 2
    assert d["max_level"] == 1


def test_max_level_reflects_highest_level_field() -> None:
    tables = _fixture()
    tables["community_reports"].append(_report_row("c2", 3))
    tables["communities"].append({"id": "c2", "level": 3})
    report = check_artifacts(tables)
    assert report.ok is True
    assert report.max_level == 3
    assert report.n_communities == 3
    assert report.n_reports == 3


def test_flat_single_level_hierarchy_fails() -> None:
    tables = _fixture()
    tables["community_reports"] = [_report_row("c0", 0)]
    tables["communities"] = [{"id": "c0", "level": 0}]
    report = check_artifacts(tables)
    assert report.ok is False
    assert report.max_level == 0
    assert any("flat hierarchy" in e for e in report.errors)


def test_constants_shape() -> None:
    assert {
        "entities",
        "relationships",
        "text_units",
        "communities",
        "community_reports",
    } == REQUIRED_TABLES
    assert {"community_id", "title", "summary", "level", "rank", "findings"} == REPORT_COLUMNS


def test_missing_multiple_tables_reported_each() -> None:
    tables = _fixture()
    del tables["entities"]
    del tables["relationships"]
    report = check_artifacts(tables)
    assert report.ok is False
    assert "missing table: entities" in report.errors
    assert "missing table: relationships" in report.errors


def test_input_not_mutated() -> None:
    tables = _fixture()
    snapshot = copy.deepcopy(tables)
    check_artifacts(tables)
    assert tables == snapshot

"""Tests for §11.4 GraphRAG build integrity / Тесты целостности сборки."""

from __future__ import annotations

import json

from kg_retrievers.graphrag_build_integrity import (
    BuildIntegrityReport,
    check_build,
)


def _report(community_id: str, level: int, summary: str = "text") -> dict:
    """Build a well-formed report / Собрать корректный отчёт."""
    return {
        "title": f"C{community_id}",
        "summary": summary,
        "rank": 5,
        "level": level,
        "community_id": community_id,
    }


def _valid_build() -> tuple[list[dict], list[dict]]:
    """Return a valid 3-community/3-report 2-level build / Валидная сборка."""
    communities = [
        {"community_id": "a", "level": 0},
        {"community_id": "b", "level": 0},
        {"community_id": "c", "level": 1},
    ]
    reports = [
        _report("a", 0),
        _report("b", 0),
        _report("c", 1),
    ]
    return communities, reports


def test_valid_build_is_ok() -> None:
    """(1) valid 3/3 2-level -> ok, no errors, levels==(0,1)."""
    communities, reports = _valid_build()
    result = check_build(communities, reports)
    assert result.ok is True
    assert result.errors == ()
    assert result.n_communities == 3
    assert result.n_reports == 3
    assert result.levels == (0, 1)


def test_empty_communities_flags_error() -> None:
    """(2) empty communities -> ok=False with 'no communities' error."""
    _, reports = _valid_build()
    result = check_build([], reports)
    assert result.ok is False
    assert result.n_communities == 0
    assert any("no communities" in err for err in result.errors)


def test_missing_summary_reduces_n_reports() -> None:
    """(3) a report missing summary reduces n_reports and flags error."""
    communities, reports = _valid_build()
    reports[2] = {
        "title": "Cc",
        "rank": 5,
        "level": 1,
        "community_id": "c",
    }
    result = check_build(communities, reports)
    assert result.ok is False
    assert result.n_reports == 2
    assert any("summary" in err for err in result.errors)


def test_single_level_build_fails_min_levels() -> None:
    """(4) single-level build with min_levels=2 -> ok=False."""
    communities = [
        {"community_id": "a", "level": 0},
        {"community_id": "b", "level": 0},
    ]
    reports = [_report("a", 0), _report("b", 0)]
    result = check_build(communities, reports, min_levels=2)
    assert result.ok is False
    assert result.levels == (0,)
    assert any("insufficient levels" in err for err in result.errors)


def test_missing_rank_key_mentions_rank() -> None:
    """(5) report missing required key `rank` adds error mentioning 'rank'."""
    communities, reports = _valid_build()
    del reports[0]["rank"]
    result = check_build(communities, reports)
    assert result.ok is False
    assert any("rank" in err for err in result.errors)


def test_levels_sorted_and_deduplicated() -> None:
    """(6) levels tuple is sorted and deduplicated."""
    communities = [
        {"community_id": "a", "level": 2},
        {"community_id": "b", "level": 0},
        {"community_id": "c", "level": 2},
        {"community_id": "d", "level": 1},
    ]
    reports = [
        _report("a", 2),
        _report("b", 0),
        _report("c", 2),
        _report("d", 1),
    ]
    result = check_build(communities, reports, min_levels=3)
    assert result.levels == (0, 1, 2)
    assert result.ok is True


def test_as_dict_round_trips_through_json() -> None:
    """(7) as_dict round-trips through json.dumps."""
    communities, reports = _valid_build()
    result = check_build(communities, reports)
    encoded = json.dumps(result.as_dict())
    decoded = json.loads(encoded)
    assert decoded == {
        "ok": True,
        "n_communities": 3,
        "n_reports": 3,
        "levels": [0, 1],
        "errors": [],
    }
    assert isinstance(result, BuildIntegrityReport)

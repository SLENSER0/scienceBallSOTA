"""Tests for community-report quality scoring (§11.18)."""

from __future__ import annotations

import json

from kg_retrievers.community_report_quality import (
    ReportQuality,
    rank_by_quality,
    score_report,
)


def _full_report(community_id: int = 1) -> dict:
    return {
        "community_id": community_id,
        "title": "Superconductivity cluster",
        "summary": "A dense summary of the community spanning well over forty chars.",
        "findings": [{"text": "f1"}, {"text": "f2"}],
        "rank": 7,
        "doc_ids": ["d1", "d2", "d3"],
    }


def test_full_report_complete_and_no_flags() -> None:
    q = score_report(_full_report())
    assert q.completeness == 1.0
    assert q.flags == ()
    assert q.n_findings == 2
    assert q.has_sources is True


def test_empty_summary_short_flag_and_lower_completeness() -> None:
    report = _full_report()
    report["summary"] = ""
    q = score_report(report)
    assert "short_summary" in q.flags
    assert q.summary_len == 0
    # summary missing -> 4/5 required fields present.
    assert q.completeness == 0.8


def test_no_findings_flag_and_zero_count() -> None:
    report = _full_report()
    report["findings"] = []
    q = score_report(report)
    assert q.n_findings == 0
    assert "no_findings" in q.flags


def test_empty_doc_ids_no_sources() -> None:
    report = _full_report()
    report["doc_ids"] = []
    q = score_report(report)
    assert q.has_sources is False
    assert "no_sources" in q.flags


def test_score_within_unit_interval() -> None:
    good = score_report(_full_report())
    empty = score_report({})
    assert 0.0 <= good.score <= 1.0
    assert 0.0 <= empty.score <= 1.0
    # A fully populated report must outscore an empty one.
    assert good.score > empty.score
    assert empty.score == 0.0


def test_rank_by_quality_highest_first() -> None:
    good = _full_report(community_id=10)
    weak = {
        "community_id": 20,
        "title": "Sparse",
        "summary": "tiny",
        "findings": [],
        "doc_ids": [],
    }
    ranked = rank_by_quality([weak, good])
    assert [q.community_id for q in ranked] == [10, 20]
    assert ranked[0].score >= ranked[1].score


def test_as_dict_stable_and_json_serializable() -> None:
    q = score_report(_full_report())
    d = q.as_dict()
    assert set(d.keys()) == {
        "community_id",
        "completeness",
        "n_findings",
        "summary_len",
        "has_sources",
        "score",
        "flags",
    }
    encoded = json.dumps(d)
    assert isinstance(encoded, str)
    assert isinstance(d["flags"], list)


def test_reportquality_is_frozen() -> None:
    q = score_report(_full_report())
    assert isinstance(q, ReportQuality)
    try:
        q.score = 0.0  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject mutation
        raise AssertionError("ReportQuality should be frozen")

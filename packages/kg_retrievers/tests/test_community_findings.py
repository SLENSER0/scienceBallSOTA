"""§11.4/§11.7 — tests for findings normalization & cross-report ranking."""

from __future__ import annotations

from kg_retrievers.community_findings import (
    Finding,
    normalize_findings,
    top_findings,
)


def test_empty_findings_yields_empty_list() -> None:
    report = {"community_id": 1, "level": 0, "rank": 5.0, "findings": []}
    assert normalize_findings(report) == []


def test_str_finding_has_empty_explanation() -> None:
    report = {"community_id": 7, "level": 1, "rank": 3.0, "findings": ["Alpha claim"]}
    (finding,) = normalize_findings(report)
    assert finding.summary == "Alpha claim"
    assert finding.explanation == ""
    assert finding.community_id == 7
    assert finding.level == 1
    assert finding.rank == 3.0


def test_dict_finding_preserves_explanation() -> None:
    report = {
        "community_id": 2,
        "level": 0,
        "rank": 1.0,
        "findings": [{"summary": "S", "explanation": "because reasons"}],
    }
    (finding,) = normalize_findings(report)
    assert finding.summary == "S"
    assert finding.explanation == "because reasons"


def test_order_equals_list_index() -> None:
    report = {
        "community_id": 3,
        "level": 0,
        "rank": 2.0,
        "findings": ["zero", "one", "two"],
    }
    findings = normalize_findings(report)
    assert [f.order for f in findings] == [0, 1, 2]
    # finding[1] -> order 1
    assert findings[1].order == 1
    assert findings[1].summary == "one"


def test_top_findings_higher_rank_first() -> None:
    low = {"community_id": 1, "level": 0, "rank": 1.0, "findings": ["low one"]}
    high = {"community_id": 2, "level": 0, "rank": 9.0, "findings": ["high one"]}
    ranked = top_findings([low, high], k=10)
    assert ranked[0].summary == "high one"
    assert ranked[1].summary == "low one"


def test_top_findings_dedupes_across_reports() -> None:
    a = {"community_id": 1, "level": 0, "rank": 5.0, "findings": ["Shared Claim"]}
    b = {"community_id": 2, "level": 0, "rank": 2.0, "findings": ["shared claim"]}
    ranked = top_findings([a, b], k=10)
    assert len(ranked) == 1
    # first (higher-rank) occurrence kept
    assert ranked[0].community_id == 1
    assert ranked[0].summary == "Shared Claim"


def test_top_findings_caps_at_k() -> None:
    report = {
        "community_id": 1,
        "level": 0,
        "rank": 1.0,
        "findings": ["a", "b", "c", "d", "e"],
    }
    ranked = top_findings([report], k=2)
    assert len(ranked) == 2


def test_as_dict_has_exactly_six_keys() -> None:
    finding = Finding(
        community_id=1,
        level=2,
        order=3,
        summary="s",
        explanation="e",
        rank=4.0,
    )
    d = finding.as_dict()
    assert set(d.keys()) == {
        "community_id",
        "level",
        "order",
        "summary",
        "explanation",
        "rank",
    }
    assert len(d) == 6
    assert d == {
        "community_id": 1,
        "level": 2,
        "order": 3,
        "summary": "s",
        "explanation": "e",
        "rank": 4.0,
    }

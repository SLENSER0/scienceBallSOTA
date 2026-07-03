"""§13.15 tests for the gap_analyzer aggregator / тесты узла gap_analyzer."""

from __future__ import annotations

import pytest
from agent_service.gap_finding import (
    CRITICAL_TYPES,
    GAP_TYPES,
    GapFinding,
    aggregate_gaps,
    is_critical,
    needs_review,
)


def test_taxonomy_membership() -> None:
    """§11.1 taxonomy has all 11 kinds and CRITICAL_TYPES is a subset."""
    assert len(GAP_TYPES) == 11
    assert "orphan_entity" in GAP_TYPES
    assert CRITICAL_TYPES <= GAP_TYPES


def test_unknown_type_raises() -> None:
    """Assertion (1): an unknown gap type raises ValueError."""
    with pytest.raises(ValueError, match="unknown gap type"):
        GapFinding(type="not_a_gap", entity_id="e1", description="x", severity=0.5)


def test_severity_out_of_range_raises() -> None:
    """Assertion (2): severity 1.5 raises ValueError."""
    with pytest.raises(ValueError, match="out of range"):
        GapFinding(type="missing_unit", entity_id="e1", description="x", severity=1.5)


def test_severity_boundaries_accepted() -> None:
    """Both 0.0 and 1.0 are valid severities (closed interval)."""
    assert GapFinding("missing_unit", "e1", "x", 0.0).severity == 0.0
    assert GapFinding("missing_unit", "e1", "x", 1.0).severity == 1.0


def test_dedupe_keeps_max_severity() -> None:
    """Assertion (3): same (type, entity_id) collapses to one with max severity."""
    raw = [
        {"type": "missing_unit", "entity_id": "e1", "description": "lo", "severity": 0.2},
        {"type": "missing_unit", "entity_id": "e1", "description": "hi", "severity": 0.8},
    ]
    out = aggregate_gaps(raw)
    assert len(out) == 1
    assert out[0].severity == 0.8
    assert out[0].description == "hi"


def test_output_sorted_highest_first() -> None:
    """Assertion (4): aggregate output is sorted highest-severity-first."""
    raw = [
        {"type": "missing_unit", "entity_id": "a", "description": "", "severity": 0.3},
        {"type": "orphan_entity", "entity_id": "b", "description": "", "severity": 0.9},
        {"type": "missing_baseline", "entity_id": "c", "description": "", "severity": 0.6},
    ]
    out = aggregate_gaps(raw)
    severities = [g.severity for g in out]
    assert severities == sorted(severities, reverse=True)
    assert severities == [0.9, 0.6, 0.3]


def test_sort_tiebreak_by_type_ascending() -> None:
    """On equal severity, findings sort by type ascending."""
    raw = [
        {"type": "orphan_entity", "entity_id": "a", "description": "", "severity": 0.5},
        {"type": "missing_unit", "entity_id": "b", "description": "", "severity": 0.5},
    ]
    out = aggregate_gaps(raw)
    assert [g.type for g in out] == ["missing_unit", "orphan_entity"]


def test_is_critical() -> None:
    """Assertion (5): is_critical True for missing_baseline, False for missing_unit."""
    baseline = GapFinding("missing_baseline", "e1", "", 0.5)
    unit = GapFinding("missing_unit", "e1", "", 0.5)
    assert is_critical(baseline) is True
    assert is_critical(unit) is False


def test_needs_review_returns_only_critical() -> None:
    """Assertion (6): needs_review returns only critical findings, order preserved."""
    findings = aggregate_gaps(
        [
            {"type": "unverified_claim", "entity_id": "a", "description": "", "severity": 0.9},
            {"type": "missing_unit", "entity_id": "b", "description": "", "severity": 0.7},
            {"type": "missing_source_span", "entity_id": "c", "description": "", "severity": 0.5},
        ]
    )
    review = needs_review(findings)
    assert {g.type for g in review} == {"unverified_claim", "missing_source_span"}
    assert all(is_critical(g) for g in review)
    # order preserved from the aggregated (severity-sorted) input
    assert [g.severity for g in review] == [0.9, 0.5]


def test_as_dict_round_trips_all_fields() -> None:
    """Assertion (7): as_dict round-trips all four fields."""
    g = GapFinding("conflicting_measurements", "e42", "two values", 0.75)
    d = g.as_dict()
    assert d == {
        "type": "conflicting_measurements",
        "entity_id": "e42",
        "description": "two values",
        "severity": 0.75,
    }
    restored = GapFinding(**d)
    assert restored == g


def test_empty_input() -> None:
    """Aggregating an empty raw list yields an empty list."""
    assert aggregate_gaps([]) == []
    assert needs_review([]) == []

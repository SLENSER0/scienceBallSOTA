"""Tests for report data-reference resolvability check (§11.11).

Тесты для проверки разрешимости встроенных ссылок ``[Data: …]``.
"""

from __future__ import annotations

from kg_retrievers.community_report_reference_check import (
    RefCheckResult,
    check_references,
)


def test_mixed_resolved_and_dangling() -> None:
    """Entity 99 is dangling; entity 5 and report 7 resolve (2 of 3)."""
    result = check_references(
        "[Data: Entities (5, 99); Reports (7)]",
        known_entity_ids={5},
        known_report_ids={7, 8},
    )
    assert result.total_refs == 3
    assert result.resolved_refs == 2
    assert result.dangling == {"Entities": (99,)}
    assert abs(result.resolved_fraction - 2 / 3) < 1e-9


def test_empty_text_is_vacuously_resolved() -> None:
    """No references -> total 0 and a vacuous fraction of 1.0."""
    result = check_references("")
    assert result.total_refs == 0
    assert result.resolved_refs == 0
    assert result.dangling == {}
    assert result.resolved_fraction == 1.0


def test_all_resolved_has_no_dangling() -> None:
    """Every id known -> empty dangling and full fraction."""
    result = check_references(
        "[Data: Entities (5, 6)]",
        known_entity_ids={5, 6, 7},
    )
    assert result.dangling == {}
    assert result.resolved_refs == 2
    assert result.total_refs == 2
    assert result.resolved_fraction == 1.0
    assert result.as_dict()["resolved_refs"] == 2


def test_unknown_record_type_all_dangling() -> None:
    """Ids of an unknown record type are all dangling under that type key."""
    result = check_references("[Data: Claims (1, 2)]", known_entity_ids={1, 2})
    assert result.total_refs == 2
    assert result.resolved_refs == 0
    assert result.dangling == {"Claims": (1, 2)}
    assert result.resolved_fraction == 0.0


def test_relationships_resolution() -> None:
    """Relationship ids resolve against known_relationship_ids only."""
    result = check_references(
        "[Data: Relationships (3, 4)]",
        known_relationship_ids={3},
    )
    assert result.dangling == {"Relationships": (4,)}
    assert result.resolved_refs == 1


def test_result_is_frozen() -> None:
    """RefCheckResult is an immutable frozen dataclass."""
    result = check_references("[Data: Reports (7)]", known_report_ids={7})
    assert isinstance(result, RefCheckResult)
    try:
        result.total_refs = 99  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("RefCheckResult must be frozen")


def test_as_dict_serializes_dangling_as_lists() -> None:
    """as_dict converts dangling id tuples to JSON-friendly lists."""
    result = check_references("[Data: Entities (9)]")
    payload = result.as_dict()
    assert payload["dangling"] == {"Entities": [9]}
    assert payload["total_refs"] == 1
    assert payload["resolved_fraction"] == 0.0

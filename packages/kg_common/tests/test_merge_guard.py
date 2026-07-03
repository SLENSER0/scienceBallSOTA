"""Tests for the ``merge`` verified-field conflict guard (§16.6)."""

from __future__ import annotations

from kg_common.storage.merge_guard import MergeCheck, canonical_id, check_merge


def test_conflicting_verified_field_blocks_merge() -> None:
    """Two entities verified on 'value' with 5 and 7 -> disallowed, conflict reported."""
    entities = [
        {"id": "a", "value": 5, "verified_fields": ["value"]},
        {"id": "b", "value": 7, "verified_fields": ["value"]},
    ]
    result = check_merge(entities)
    assert result.allowed is False
    assert result.conflicting_fields == ["value"]


def test_override_allows_merge_but_keeps_conflict() -> None:
    """override=True forces allowed while still reporting conflicting fields."""
    entities = [
        {"id": "a", "value": 5, "verified_fields": ["value"]},
        {"id": "b", "value": 7, "verified_fields": ["value"]},
    ]
    result = check_merge(entities, override=True)
    assert result.allowed is True
    assert result.conflicting_fields == ["value"]


def test_matching_verified_values_allow_merge() -> None:
    """Same verified value on both entities -> no conflict, merge allowed."""
    entities = [
        {"id": "a", "value": 5, "verified_fields": ["value"]},
        {"id": "b", "value": 5, "verified_fields": ["value"]},
    ]
    result = check_merge(entities)
    assert result.allowed is True
    assert result.conflicting_fields == []


def test_field_verified_in_only_one_entity_is_not_a_conflict() -> None:
    """A field verified on a single entity has nothing to disagree with."""
    entities = [
        {"id": "a", "value": 5, "verified_fields": ["value"]},
        {"id": "b", "value": 7, "verified_fields": []},
    ]
    result = check_merge(entities)
    assert result.allowed is True
    assert result.conflicting_fields == []


def test_canonical_id_picks_higher_degree() -> None:
    """The entity with the largest degree wins."""
    entities = [
        {"id": "a", "degree": 2},
        {"id": "b", "degree": 9},
        {"id": "c", "degree": 5},
    ]
    assert canonical_id(entities) == "b"


def test_canonical_id_tie_returns_smaller_id() -> None:
    """On equal degree the lexicographically smallest id wins."""
    entities = [
        {"id": "z", "degree": 4},
        {"id": "a", "degree": 4},
        {"id": "m", "degree": 4},
    ]
    assert canonical_id(entities) == "a"


def test_as_dict_round_trips_reason() -> None:
    """as_dict() preserves the reason string and other fields."""
    check = MergeCheck(allowed=False, conflicting_fields=["value"], reason="blocked here")
    dumped = check.as_dict()
    assert dumped["reason"] == "blocked here"
    assert dumped["allowed"] is False
    assert dumped["conflicting_fields"] == ["value"]

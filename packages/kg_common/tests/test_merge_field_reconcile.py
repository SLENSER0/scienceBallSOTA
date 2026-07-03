"""Tests for canonical field reconciliation on a ``merge`` action (§16.6)."""

from __future__ import annotations

import pytest

from kg_common.storage.merge_field_reconcile import (
    MergedNode,
    field_winner,
    reconcile_fields,
)


def test_verified_beats_higher_confidence() -> None:
    """(1) Verified field on B wins over a higher-confidence unverified value on A."""
    entities = [
        {"id": "a", "name": "A", "value": 5, "confidence": 0.99, "verified_fields": []},
        {"id": "b", "name": "B", "value": 7, "confidence": 0.10, "verified_fields": ["value"]},
    ]
    merged = reconcile_fields(entities, canonical_id="a")
    assert merged.fields["value"] == 7
    assert merged.provenance["value"] == "b"


def test_higher_confidence_wins_between_unverified() -> None:
    """(2) Two unverified values: confidence 0.9 beats 0.5."""
    entities = [
        {"id": "a", "name": "A", "value": 5, "confidence": 0.5},
        {"id": "b", "name": "B", "value": 7, "confidence": 0.9},
    ]
    merged = reconcile_fields(entities, canonical_id="a")
    assert merged.fields["value"] == 7
    assert merged.provenance["value"] == "b"


def test_equal_confidence_newer_valid_from_wins() -> None:
    """(3) Equal confidence -> newer ``valid_from`` ISO timestamp wins."""
    entities = [
        {"id": "a", "name": "A", "value": 5, "confidence": 0.7, "valid_from": "2026-01-01"},
        {"id": "b", "name": "B", "value": 7, "confidence": 0.7, "valid_from": "2026-06-30"},
    ]
    merged = reconcile_fields(entities, canonical_id="a")
    assert merged.fields["value"] == 7
    assert merged.provenance["value"] == "b"


def test_none_never_chosen_over_non_null() -> None:
    """(4) A None value never wins over a non-null one, even with higher confidence."""
    entities = [
        {"id": "a", "name": "A", "value": None, "confidence": 0.99},
        {"id": "b", "name": "B", "value": 7, "confidence": 0.01},
    ]
    merged = reconcile_fields(entities, canonical_id="a")
    assert merged.fields["value"] == 7
    assert merged.provenance["value"] == "b"
    assert field_winner(entities, "value") == "b"


def test_aliases_union_dedup_includes_names() -> None:
    """(5) Aliases union is de-duplicated and includes both source names."""
    entities = [
        {"id": "a", "name": "Iron", "aliases": ["Fe", "ferrum"]},
        {"id": "b", "name": "Steel", "aliases": ["Fe"]},  # "Fe" duplicated
    ]
    merged = reconcile_fields(entities, canonical_id="a")
    assert merged.aliases == ["Fe", "ferrum", "Iron", "Steel"]
    assert merged.aliases.count("Fe") == 1
    assert "Iron" in merged.aliases and "Steel" in merged.aliases


def test_superseded_ids_lists_all_non_canonical() -> None:
    """(6) superseded_ids lists every non-canonical id."""
    entities = [
        {"id": "a", "name": "A"},
        {"id": "b", "name": "B"},
        {"id": "c", "name": "C"},
    ]
    merged = reconcile_fields(entities, canonical_id="b")
    assert merged.superseded_ids == ["a", "c"]
    assert "b" not in merged.superseded_ids


def test_empty_entities_raises() -> None:
    """(7) Empty entities -> ValueError."""
    with pytest.raises(ValueError):
        reconcile_fields([], canonical_id="a")


def test_as_dict_round_trips_fields_and_provenance() -> None:
    """(8) as_dict() round-trips the fields and provenance keys."""
    entities = [
        {"id": "a", "name": "A", "value": 5, "grade": "x", "confidence": 0.4},
        {"id": "b", "name": "B", "value": 7, "grade": "x", "confidence": 0.9},
    ]
    merged = reconcile_fields(entities, canonical_id="a")
    payload = merged.as_dict()
    assert isinstance(payload, dict)
    assert payload["canonical_id"] == "a"
    assert set(payload["fields"]) == set(merged.fields)
    assert set(payload["provenance"]) == set(merged.provenance)
    assert payload["fields"]["value"] == 7
    assert payload["provenance"]["value"] == "b"
    # Round-trip: rebuilding from the dict yields an equal node.
    assert MergedNode(**payload) == merged


def test_field_winner_none_when_all_null() -> None:
    """field_winner returns None when no entity carries a non-null value."""
    entities = [
        {"id": "a", "value": None},
        {"id": "b"},  # field missing entirely
    ]
    assert field_winner(entities, "value") is None
    merged = reconcile_fields(entities, canonical_id="a")
    assert "value" not in merged.fields

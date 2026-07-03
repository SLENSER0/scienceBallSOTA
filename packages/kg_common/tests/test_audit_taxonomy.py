"""Tests for the audit taxonomy — тесты таксономии аудита (§10.8)."""

from __future__ import annotations

import pytest

from kg_common.audit_taxonomy import (
    API_ACTIONS,
    API_TARGETS,
    AUDIT_ACTIONS,
    AUDIT_TARGET_TYPES,
    CURATION_ACTIONS,
    CURATION_TARGETS,
    AuditVocabulary,
    is_valid_action,
    is_valid_target,
    normalize_action,
    validate_event,
)


def test_curation_actions_exact() -> None:
    expected = frozenset(
        {"accept", "reject", "correct", "merge", "split", "alias_add", "schema_change"}
    )
    assert expected == CURATION_ACTIONS
    assert len(CURATION_ACTIONS) == 7


def test_api_actions_exact() -> None:
    expected = frozenset({"ingest", "review", "upload"})
    assert expected == API_ACTIONS
    assert len(API_ACTIONS) == 3


def test_audit_actions_is_union_of_ten() -> None:
    assert AUDIT_ACTIONS == CURATION_ACTIONS | API_ACTIONS
    assert len(AUDIT_ACTIONS) == 10
    assert "merge" in AUDIT_ACTIONS
    assert "upload" in AUDIT_ACTIONS


def test_curation_and_api_actions_disjoint() -> None:
    assert CURATION_ACTIONS.isdisjoint(API_ACTIONS)


def test_curation_targets_exact() -> None:
    expected = frozenset({"edge", "evidence", "node", "schema"})
    assert expected == CURATION_TARGETS


def test_api_targets_exact() -> None:
    expected = frozenset({"document", "job", "source"})
    assert expected == API_TARGETS


def test_audit_target_types_union_of_seven() -> None:
    assert AUDIT_TARGET_TYPES == CURATION_TARGETS | API_TARGETS
    assert len(AUDIT_TARGET_TYPES) == 7


def test_constants_are_frozensets() -> None:
    for value in (
        CURATION_ACTIONS,
        API_ACTIONS,
        AUDIT_ACTIONS,
        CURATION_TARGETS,
        API_TARGETS,
        AUDIT_TARGET_TYPES,
    ):
        assert isinstance(value, frozenset)


def test_is_valid_action_known() -> None:
    assert is_valid_action("schema_change") is True
    assert is_valid_action("accept") is True
    assert is_valid_action("ingest") is True


def test_is_valid_action_unknown() -> None:
    assert is_valid_action("delete") is False
    assert is_valid_action("MERGE") is False  # case-sensitive, not normalized
    assert is_valid_action("") is False


def test_is_valid_target_known_and_unknown() -> None:
    assert is_valid_target("source") is True
    assert is_valid_target("node") is True
    assert is_valid_target("planet") is False
    assert is_valid_target("") is False


def test_validate_event_true() -> None:
    assert validate_event("ingest", "job") is True
    assert validate_event("accept", "node") is True
    assert validate_event("schema_change", "schema") is True


def test_validate_event_false() -> None:
    assert validate_event("ingest", "planet") is False
    assert validate_event("delete", "job") is False
    assert validate_event("delete", "planet") is False


def test_normalize_action_strips_and_lowers() -> None:
    assert normalize_action(" MERGE ") == "merge"
    assert normalize_action("Upload") == "upload"
    assert normalize_action("schema_change") == "schema_change"


def test_normalize_action_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown audit action"):
        normalize_action("nope")
    with pytest.raises(ValueError):
        normalize_action("  delete ")


def test_vocabulary_as_dict_sorted() -> None:
    vocab = AuditVocabulary()
    payload = vocab.as_dict()
    assert payload["actions"] == sorted(AUDIT_ACTIONS)
    assert payload["target_types"] == sorted(AUDIT_TARGET_TYPES)
    assert payload["actions"] == payload["actions"]  # deterministic
    assert len(payload["actions"]) == 10
    assert len(payload["target_types"]) == 7


def test_vocabulary_is_frozen() -> None:
    vocab = AuditVocabulary()
    with pytest.raises(AttributeError):
        vocab.actions = frozenset()  # type: ignore[misc]

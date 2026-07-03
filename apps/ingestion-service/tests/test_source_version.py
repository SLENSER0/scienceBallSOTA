"""Tests for the §5.4 source version decision policy.

Проверки политики версионирования источника: новый источник, дубликат, новая версия.
"""

from __future__ import annotations

from ingestion_service.source_version import VersionDecision, decide_version


def test_empty_existing_is_new_source() -> None:
    """No prior rows -> brand-new source at version 1, not a duplicate, no source_id."""
    d = decide_version("hashA", "doc-1", [])
    assert d.action == "new_source"
    assert d.version == 1
    assert d.duplicate is False
    assert d.source_id is None


def test_matching_hash_is_duplicate_echoing_row() -> None:
    """A byte-identical hash -> duplicate that echoes the existing version and source_id."""
    existing = [
        {"file_hash": "hashA", "logical_key": "doc-1", "version": 3, "source_id": "src-7"},
    ]
    d = decide_version("hashA", "doc-1", existing)
    assert d.action == "duplicate"
    assert d.duplicate is True
    assert d.version == 3
    assert d.source_id == "src-7"


def test_same_logical_key_different_hash_is_new_version() -> None:
    """Same logical key but new content -> new_version at max(existing versions)+1."""
    existing = [
        {"file_hash": "hashA", "logical_key": "doc-1", "version": 1, "source_id": "src-1"},
        {"file_hash": "hashB", "logical_key": "doc-1", "version": 2, "source_id": "src-2"},
    ]
    d = decide_version("hashC", "doc-1", existing)
    assert d.action == "new_version"
    assert d.version == 3
    assert d.duplicate is False
    assert d.source_id is None


def test_different_logical_key_is_new_source() -> None:
    """A logical key unseen in the registry -> new_source at version 1."""
    existing = [
        {"file_hash": "hashA", "logical_key": "doc-1", "version": 5, "source_id": "src-1"},
    ]
    d = decide_version("hashZ", "doc-99", existing)
    assert d.action == "new_source"
    assert d.version == 1
    assert d.duplicate is False
    assert d.source_id is None


def test_duplicate_branch_never_increments_version() -> None:
    """Even with higher versions of the same key present, a hash hit echoes its own version."""
    existing = [
        {"file_hash": "hashA", "logical_key": "doc-1", "version": 2, "source_id": "src-2"},
        {"file_hash": "hashB", "logical_key": "doc-1", "version": 9, "source_id": "src-9"},
    ]
    d = decide_version("hashA", "doc-1", existing)
    assert d.action == "duplicate"
    assert d.version == 2
    assert d.duplicate is True
    assert d.source_id == "src-2"


def test_hash_match_wins_over_logical_key_mismatch() -> None:
    """Idempotency: a hash hit is a duplicate even if the supplied logical_key differs."""
    existing = [
        {"file_hash": "hashA", "logical_key": "doc-1", "version": 4, "source_id": "src-4"},
    ]
    d = decide_version("hashA", "doc-renamed", existing)
    assert d.action == "duplicate"
    assert d.version == 4
    assert d.source_id == "src-4"


def test_as_dict_roundtrip_and_action_is_str() -> None:
    """as_dict() exposes the four fields and action serialises to a plain str."""
    d = decide_version("hashNew", "doc-new", [])
    payload = d.as_dict()
    assert isinstance(payload["action"], str)
    assert payload == {
        "action": "new_source",
        "version": 1,
        "duplicate": False,
        "source_id": None,
    }


def test_decision_is_frozen() -> None:
    """VersionDecision is an immutable frozen dataclass."""
    d = VersionDecision(action="new_source", version=1, duplicate=False, source_id=None)
    try:
        d.version = 2  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("VersionDecision must be frozen")

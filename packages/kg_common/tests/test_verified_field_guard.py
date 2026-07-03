"""Tests for verified-field upsert guard (§16.8) — hand-checkable cases."""

from __future__ import annotations

from kg_common.storage.verified_field_guard import (
    GuardResult,
    filter_upsert,
    needs_review_task,
)


def test_non_verified_applied_verified_skipped_same_value() -> None:
    # 'b' is verified with same value → applied={'a':1}, skipped=['b'], no conflict
    result = filter_upsert({"a": 1, "b": 2}, ["b"], {"b": 2})
    assert result.applied == {"a": 1}
    assert result.skipped == ["b"]
    assert result.conflicts == []


def test_verified_differing_value_is_conflict_and_not_applied() -> None:
    result = filter_upsert({"b": 9}, ["b"], {"b": 2})
    assert result.applied == {}
    assert result.conflicts == ["b"]
    assert result.skipped == ["b"]


def test_verified_same_value_no_conflict() -> None:
    result = filter_upsert({"b": 2}, ["b"], {"b": 2})
    assert result.conflicts == []
    assert result.skipped == ["b"]
    assert result.applied == {}


def test_empty_verified_fields_applies_everything() -> None:
    incoming = {"a": 1, "b": 2}
    result = filter_upsert(incoming, [], {"b": 2})
    assert result.applied == incoming
    assert result.skipped == []
    assert result.conflicts == []


def test_verified_absent_from_current_counts_as_conflict() -> None:
    # incoming introduces a value for a verified field not yet stored → conflict
    result = filter_upsert({"b": 5}, ["b"], {})
    assert result.conflicts == ["b"]
    assert result.skipped == ["b"]
    assert result.applied == {}


def test_needs_review_task_true_on_conflict() -> None:
    assert needs_review_task(filter_upsert({"b": 9}, ["b"], {"b": 2})) is True


def test_needs_review_task_false_without_conflict() -> None:
    assert needs_review_task(filter_upsert({"a": 1}, ["b"], {"b": 2})) is False


def test_as_dict_keys() -> None:
    result = filter_upsert({"a": 1, "b": 9}, ["b"], {"b": 2})
    assert set(result.as_dict().keys()) == {"applied", "skipped", "conflicts"}


def test_as_dict_roundtrip_values() -> None:
    result = filter_upsert({"a": 1, "b": 9}, ["b"], {"b": 2})
    assert result.as_dict() == {
        "applied": {"a": 1},
        "skipped": ["b"],
        "conflicts": ["b"],
    }


def test_default_guardresult_is_empty() -> None:
    result = GuardResult()
    assert result.applied == {}
    assert result.skipped == []
    assert result.conflicts == []
    assert needs_review_task(result) is False


def test_multiple_verified_mixed() -> None:
    result = filter_upsert(
        {"a": 1, "b": 2, "c": 3, "d": 4},
        ["b", "c", "d"],
        {"b": 2, "c": 99},  # c differs, d absent, b same
    )
    assert result.applied == {"a": 1}
    assert result.skipped == ["b", "c", "d"]
    assert result.conflicts == ["c", "d"]
    assert needs_review_task(result) is True

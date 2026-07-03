"""Tests for the audit before/after diff builder (§19.5 audit logs)."""

from __future__ import annotations

from kg_common.security.audit_diff import (
    AuditDiff,
    FieldChange,
    changed_fields,
    compute_diff,
)


def test_single_field_modified() -> None:
    diff = compute_diff({"a": 1}, {"a": 2})
    assert diff.changes == (FieldChange("a", 1, 2),)


def test_changed_fields_reports_only_the_delta() -> None:
    diff = compute_diff({"a": 1, "b": 2}, {"a": 1, "b": 3})
    assert changed_fields(diff) == ("b",)


def test_added_key_has_none_before() -> None:
    diff = compute_diff({}, {"x": 1})
    assert diff.changes == (FieldChange("x", None, 1),)


def test_removed_key_has_none_after() -> None:
    diff = compute_diff({"x": 1}, {})
    assert diff.changes == (FieldChange("x", 1, None),)


def test_secret_field_redacted_on_both_sides() -> None:
    diff = compute_diff({"password": "old"}, {"password": "new"})
    assert diff.changes == (FieldChange("password", "***", "***"),)


def test_identical_mappings_yield_empty_diff() -> None:
    diff = compute_diff({"a": 1, "b": 2}, {"a": 1, "b": 2})
    assert diff.changes == ()
    assert diff.as_dict()["changed"] == []


def test_as_dict_before_contains_only_changed_keys() -> None:
    diff = compute_diff({"a": 1, "b": 2}, {"a": 1, "b": 3})
    payload = diff.as_dict()
    assert payload == {"before": {"b": 2}, "after": {"b": 3}, "changed": ["b"]}
    # Unchanged 'a' must not leak into either side of the payload.
    assert "a" not in payload["before"]
    assert "a" not in payload["after"]


def test_secret_added_key_masks_only_present_side() -> None:
    # A newly-set secret redacts its value but keeps None on the missing side.
    diff = compute_diff({}, {"token": "abc"})
    assert diff.changes == (FieldChange("token", None, "***"),)


def test_as_dict_is_plain_json_shaped() -> None:
    diff = compute_diff({"a": 1}, {"a": 2})
    assert diff.as_dict() == {"before": {"a": 1}, "after": {"a": 2}, "changed": ["a"]}


def test_empty_diff_is_a_frozen_dataclass() -> None:
    diff = AuditDiff(changes=())
    assert changed_fields(diff) == ()

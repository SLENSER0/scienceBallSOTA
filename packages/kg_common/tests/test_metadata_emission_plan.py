"""Tests for the idempotent emission plan — тесты (§10.4)."""

from __future__ import annotations

import pytest

from kg_common.metadata.emission_plan import (
    EmissionAction,
    plan_batch,
    plan_emission,
)


def test_unknown_source_is_create() -> None:
    """A source absent from ``existing`` is a ``create``."""
    action = plan_emission({"source_id": "s", "file_hash": "h1", "version": 1}, {})
    assert action.op == "create"
    assert action.reason == "new_source"
    assert action.source_id == "s"


def test_identical_hash_and_version_is_skip() -> None:
    """Same ``file_hash`` and ``version`` -> ``skip`` (``unchanged``)."""
    existing = {"s": {"source_id": "s", "file_hash": "h1", "version": 1}}
    action = plan_emission({"source_id": "s", "file_hash": "h1", "version": 1}, existing)
    assert action.op == "skip"
    assert action.reason == "unchanged"


def test_changed_hash_is_update_content_changed() -> None:
    """A different ``file_hash`` -> ``update`` with reason ``content_changed``."""
    existing = {"s": {"source_id": "s", "file_hash": "h1", "version": 1}}
    action = plan_emission({"source_id": "s", "file_hash": "h2", "version": 1}, existing)
    assert action.op == "update"
    assert action.reason == "content_changed"


def test_same_hash_higher_version_is_version_bump() -> None:
    """Same hash but version 2 vs existing 1 -> ``update`` reason ``version_bump``."""
    existing = {"s": {"source_id": "s", "file_hash": "h1", "version": 1}}
    action = plan_emission({"source_id": "s", "file_hash": "h1", "version": 2}, existing)
    assert action.op == "update"
    assert action.reason == "version_bump"


def test_lower_or_equal_version_same_hash_is_skip() -> None:
    """Same hash with a non-higher version is still ``skip`` — not a bump."""
    existing = {"s": {"source_id": "s", "file_hash": "h1", "version": 5}}
    action = plan_emission({"source_id": "s", "file_hash": "h1", "version": 3}, existing)
    assert action.op == "skip"
    assert action.reason == "unchanged"


def test_content_change_wins_over_version() -> None:
    """A hash change is reported as ``content_changed`` even when version bumps too."""
    existing = {"s": {"source_id": "s", "file_hash": "h1", "version": 1}}
    action = plan_emission({"source_id": "s", "file_hash": "h9", "version": 7}, existing)
    assert action.op == "update"
    assert action.reason == "content_changed"


def test_plan_twice_on_create_result_is_idempotent() -> None:
    """Re-planning a ``create`` after it lands in ``existing`` yields ``skip``."""
    incoming = {"source_id": "s", "file_hash": "h1", "version": 1}
    first = plan_emission(incoming, {})
    assert first.op == "create"
    # The create is now materialized in the existing snapshot.
    existing = {first.source_id: dict(incoming)}
    second = plan_emission(incoming, existing)
    assert second.op == "skip"
    assert second.reason == "unchanged"


def test_plan_batch_preserves_input_order() -> None:
    """``plan_batch`` returns actions aligned to input order."""
    existing = {"b": {"source_id": "b", "file_hash": "hb", "version": 1}}
    incomings = [
        {"source_id": "a", "file_hash": "ha", "version": 1},  # create
        {"source_id": "b", "file_hash": "hb", "version": 1},  # skip
        {"source_id": "c", "file_hash": "hc", "version": 1},  # create
    ]
    actions = plan_batch(incomings, existing)
    assert [a.source_id for a in actions] == ["a", "b", "c"]
    assert [a.op for a in actions] == ["create", "skip", "create"]


def test_plan_batch_empty_is_empty() -> None:
    """An empty batch plans to an empty list."""
    assert plan_batch([], {}) == []


def test_as_dict_shape_and_op() -> None:
    """``as_dict`` exposes the three fields and preserves ``op``."""
    d = EmissionAction("s", "skip", "unchanged").as_dict()
    assert d == {"source_id": "s", "op": "skip", "reason": "unchanged"}
    assert d["op"] == "skip"


def test_emission_action_is_frozen() -> None:
    """:class:`EmissionAction` is immutable — frozen dataclass."""
    action = EmissionAction("s", "create", "new_source")
    with pytest.raises((AttributeError, TypeError)):
        action.op = "skip"  # type: ignore[misc]


def test_emission_action_rejects_unknown_op() -> None:
    """Constructing with an out-of-set ``op`` raises ``ValueError``."""
    with pytest.raises(ValueError):
        EmissionAction("s", "delete", "x")


def test_missing_version_defaults_to_zero() -> None:
    """A missing ``version`` defaults to 0, so 1 vs absent is a ``version_bump``."""
    existing = {"s": {"source_id": "s", "file_hash": "h1"}}
    action = plan_emission({"source_id": "s", "file_hash": "h1", "version": 1}, existing)
    assert action.op == "update"
    assert action.reason == "version_bump"

"""Tests for §16.4 review-task dedup key + collision-merge reconciliation.

RU/EN: Hand-checkable checks for :mod:`kg_common.storage.review_dedup` — key
stability under payload key-order, target-id sensitivity, and the create/update/
skip collision policy.
"""

from __future__ import annotations

from kg_common.storage.review_dedup import (
    ACTION_CREATED,
    ACTION_SKIPPED,
    ACTION_UPDATED,
    DedupOutcome,
    dedup_key,
    reconcile,
)


def _task(**over: object) -> dict[str, object]:
    """A base review task with the four identity fields + payload/priority/status."""
    base: dict[str, object] = {
        "task_type": "verify_measurement",
        "target_type": "Measurement",
        "target_id": "meas-42",
        "payload": {"field": "hardness", "unit": "HV", "value": 210},
        "priority": 3,
        "status": "open",
    }
    base.update(over)
    return base


def test_same_task_twice_identical_key() -> None:
    """(1) The same task hashed twice yields an identical dedup_key."""
    task = _task()
    assert dedup_key(task) == dedup_key(_task())
    assert dedup_key(task) == dedup_key(task)


def test_payload_key_order_does_not_change_key() -> None:
    """(2) Payload key-order difference is canonicalized away → same dedup_key."""
    a = _task(payload={"field": "hardness", "unit": "HV", "value": 210})
    b = _task(payload={"value": 210, "unit": "HV", "field": "hardness"})
    # Same key/value pairs, different insertion order → same canonical key.
    assert list(a["payload"]) != list(b["payload"])  # insertion order genuinely differs
    assert dedup_key(a) == dedup_key(b)


def test_different_target_id_different_key() -> None:
    """(3) A different target_id yields a different dedup_key."""
    assert dedup_key(_task(target_id="meas-42")) != dedup_key(_task(target_id="meas-99"))


def test_reconcile_none_creates() -> None:
    """(4) reconcile(new, None) → action == 'created' with the new key/payload."""
    outcome = reconcile(_task(), None)
    assert outcome.action == ACTION_CREATED
    assert outcome.dedup_key == dedup_key(_task())
    assert outcome.payload == {"field": "hardness", "unit": "HV", "value": 210}
    assert outcome.priority == 3


def test_reconcile_open_lower_priority_updates_to_max() -> None:
    """(5) Open existing with lower priority → 'updated', priority == max, merged payload."""
    new = _task(priority=7, payload={"field": "hardness", "note": "rechecked"})
    existing = _task(priority=2, payload={"field": "hardness", "unit": "HV", "value": 210})
    outcome = reconcile(new, existing)
    assert outcome.action == ACTION_UPDATED
    assert outcome.priority == 7  # max(7, 2)
    # Merged payload: existing keys preserved, new keys override/added.
    assert outcome.payload == {
        "field": "hardness",
        "unit": "HV",
        "value": 210,
        "note": "rechecked",
    }


def test_reconcile_open_higher_existing_priority_keeps_max() -> None:
    """(5b) Max is taken even when the existing task is the more urgent one."""
    outcome = reconcile(_task(priority=1), _task(priority=9))
    assert outcome.action == ACTION_UPDATED
    assert outcome.priority == 9


def test_reconcile_in_review_also_updates() -> None:
    """(5c) 'in_review' is an open state → 'updated', not skipped."""
    outcome = reconcile(_task(priority=5), _task(priority=1, status="in_review"))
    assert outcome.action == ACTION_UPDATED
    assert outcome.priority == 5


def test_reconcile_resolved_skips() -> None:
    """(6) Existing status 'resolved' → action == 'skipped'."""
    outcome = reconcile(_task(priority=8), _task(priority=2, status="resolved"))
    assert outcome.action == ACTION_SKIPPED
    assert outcome.priority == 2  # carries the existing task's priority


def test_reconcile_dismissed_skips() -> None:
    """(6b) Existing status 'dismissed' is also closed → 'skipped'."""
    assert reconcile(_task(), _task(status="dismissed")).action == ACTION_SKIPPED


def test_as_dict_dedup_key_is_64_char_hex() -> None:
    """(7) as_dict()['dedup_key'] is a 64-char lowercase hex sha256 string."""
    outcome = reconcile(_task(), None)
    d = outcome.as_dict()
    key = d["dedup_key"]
    assert isinstance(key, str)
    assert len(key) == 64
    assert all(ch in "0123456789abcdef" for ch in key)
    # as_dict round-trips all fields.
    assert set(d) == {"dedup_key", "action", "priority", "payload"}


def test_outcome_is_frozen() -> None:
    """DedupOutcome is an immutable frozen dataclass."""
    outcome = reconcile(_task(), None)
    assert isinstance(outcome, DedupOutcome)
    try:
        outcome.action = "mutated"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject assignment
        raise AssertionError("DedupOutcome should be frozen")


def test_task_type_and_target_type_affect_key() -> None:
    """Distinct task_type or target_type produce distinct keys (full tuple hashed)."""
    base = dedup_key(_task())
    assert dedup_key(_task(task_type="verify_unit")) != base
    assert dedup_key(_task(target_type="Entity")) != base

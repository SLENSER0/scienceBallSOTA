"""Revert of a multi-event decision via compensating events (§16.7).

Tests a 3-event decision on one target: plan_revert yields 3 compensating
entries in reverse order (before/after inverted), restored_status is the
pre-decision state, apply_revert records one higher-version ``reverted``
decision, preserves the audit trail and is idempotent by decision_id.
"""

from __future__ import annotations

import pytest

from kg_common.errors import NotFoundError
from kg_common.storage.decision_revert import (
    REVERT_ID_PREFIX,
    RevertPlan,
    apply_revert,
    plan_revert,
)
from kg_common.storage.decisions import Decision, DecisionStore

NOW = "2026-07-03T00:00:00+00:00"


@pytest.fixture
def store() -> DecisionStore:
    """Temp in-memory store seeded with a 3-event decision on ``ent:1``.

    Chained state: s0 → s1 → s2 → s3 (before/after hashes chain).
    """
    s = DecisionStore("sqlite:///:memory:")
    s.migrate()
    s.record_decision(
        Decision("e1", "ent:1", event_id="ev1", action="create", before_hash="s0", after_hash="s1")
    )
    s.record_decision(
        Decision("e2", "ent:1", event_id="ev2", action="merge", before_hash="s1", after_hash="s2")
    )
    s.record_decision(
        Decision("e3", "ent:1", event_id="ev3", action="correct", before_hash="s2", after_hash="s3")
    )
    return s


def test_plan_revert_yields_three_compensating_in_reverse_order(store: DecisionStore) -> None:
    plan = plan_revert(store, "e3")
    assert isinstance(plan, RevertPlan)
    assert plan.decision_id == "e3" and plan.target_id == "ent:1"
    assert len(plan.compensating) == 3
    # reverse order: last forward event (e3) is compensated first.
    assert [c["reverts_decision_id"] for c in plan.compensating] == ["e3", "e2", "e1"]
    assert plan.compensating[0] == {
        "reverts_decision_id": "e3",
        "event_id": "ev3",
        "target_id": "ent:1",
        "action": "revert",
        "before_hash": "s3",  # inverted: was after_hash
        "after_hash": "s2",  # inverted: was before_hash
    }


def test_compensating_events_invert_each_before_after(store: DecisionStore) -> None:
    plan = plan_revert(store, "e3")
    # Each compensating event swaps before_hash <-> after_hash of its forward event.
    assert [(c["before_hash"], c["after_hash"]) for c in plan.compensating] == [
        ("s3", "s2"),
        ("s2", "s1"),
        ("s1", "s0"),
    ]


def test_restored_status_matches_pre_decision_state(store: DecisionStore) -> None:
    plan = plan_revert(store, "e3")
    # Pre-decision state is the before_hash of the first forward event.
    assert plan.restored_status == "s0"


def test_apply_revert_records_higher_version_reverted_decision(store: DecisionStore) -> None:
    reverted = apply_revert(store, "e3", actor="alice", now=NOW)
    assert reverted.version == 4  # max forward version (3) + 1
    assert reverted.action == "reverted"
    assert reverted.decision_id == f"{REVERT_ID_PREFIX}e3"
    assert reverted.target_id == "ent:1"
    # New highest version on the target.
    assert store.latest_for("ent:1").decision_id == f"{REVERT_ID_PREFIX}e3"


def test_apply_revert_restores_prior_state(store: DecisionStore) -> None:
    reverted = apply_revert(store, "e3", actor="alice", now=NOW)
    # Compensation moves current state (s3) back to the pre-decision state (s0).
    assert reverted.before_hash == "s3"
    assert reverted.after_hash == "s0"
    assert reverted.after_hash == plan_revert(store, "e3").restored_status


def test_apply_revert_records_actor_and_now(store: DecisionStore) -> None:
    reverted = apply_revert(store, "e3", actor="carol", now=NOW)
    assert reverted.actor == "carol"
    assert reverted.created_at == NOW


def test_apply_revert_preserves_audit_trail(store: DecisionStore) -> None:
    apply_revert(store, "e3", actor="alice", now=NOW)
    hist = store.history_for("ent:1")
    # Original 3 forward events survive (no destructive revert) + 1 compensation.
    assert [d.decision_id for d in hist] == ["e1", "e2", "e3", f"{REVERT_ID_PREFIX}e3"]
    assert [d.version for d in hist] == [1, 2, 3, 4]


def test_second_revert_is_idempotent_noop(store: DecisionStore) -> None:
    first = apply_revert(store, "e3", actor="alice", now=NOW)
    # Second revert: deterministic id already stored -> same row, no version bump.
    second = apply_revert(store, "e3", actor="alice", now="2027-01-01T00:00:00+00:00")
    assert second.version == first.version == 4
    assert len(store.history_for("ent:1")) == 4  # no extra row
    # plan_revert stays stable: compensation is excluded from forward events.
    assert len(plan_revert(store, "e3").compensating) == 3


def test_plan_revert_unknown_decision_raises(store: DecisionStore) -> None:
    with pytest.raises(NotFoundError):
        plan_revert(store, "does-not-exist")


def test_apply_revert_unknown_decision_raises(store: DecisionStore) -> None:
    with pytest.raises(NotFoundError):
        apply_revert(store, "nope", actor="alice", now=NOW)


def test_revert_plan_as_dict(store: DecisionStore) -> None:
    data = plan_revert(store, "e3").as_dict()
    assert data["decision_id"] == "e3"
    assert data["target_id"] == "ent:1"
    assert data["restored_status"] == "s0"
    assert len(data["compensating"]) == 3
    assert data["compensating"][0]["before_hash"] == "s3"
    assert set(data) == {"decision_id", "target_id", "compensating", "restored_status"}

"""Review-task assignment + load balancing (§16.10 назначение ревью / balancing)."""

from __future__ import annotations

import pytest

from kg_common.storage.review_assignment import (
    STATUS_OPEN,
    Assignment,
    ReviewAssignment,
)

# fixed explicit timestamps (ISO-8601, lexicographically sortable)
T09 = "2026-07-03T09:00:00+00:00"
T10 = "2026-07-03T10:00:00+00:00"
T11 = "2026-07-03T11:00:00+00:00"
T12 = "2026-07-03T12:00:00+00:00"


@pytest.fixture
def store() -> ReviewAssignment:
    s = ReviewAssignment("sqlite:///:memory:")
    s.migrate()
    return s


def test_assign_and_assignments_for(store: ReviewAssignment) -> None:
    store.assign("t:1", "anna", T09)
    store.assign("t:2", "anna", T10)
    got = store.assignments_for("anna")
    assert [a.task_id for a in got] == ["t:1", "t:2"]  # oldest-first
    assert got[0] == Assignment("t:1", "anna", T09, STATUS_OPEN)
    assert got[0].assigned_at == T09
    assert got[0].status == "open"


def test_reassign_updates(store: ReviewAssignment) -> None:
    store.assign("t:1", "anna", T09)
    store.reassign("t:1", "bob", T11)
    assert store.assignments_for("anna") == []  # moved off anna
    bob = store.assignments_for("bob")
    assert len(bob) == 1
    assert bob[0].task_id == "t:1"
    assert bob[0].assignee == "bob"
    assert bob[0].assigned_at == T11  # new timestamp recorded


def test_reassign_unknown_task_is_noop(store: ReviewAssignment) -> None:
    store.reassign("t:missing", "bob", T11)  # no existing row -> nothing created
    assert store.assignments_for("bob") == []
    assert store.load_by_assignee() == {}


def test_load_by_assignee_counts(store: ReviewAssignment) -> None:
    store.assign("t:1", "anna", T09)
    store.assign("t:2", "anna", T10)
    store.assign("t:3", "bob", T09)
    assert store.load_by_assignee() == {"anna": 2, "bob": 1}


def test_least_loaded_picks_fewest(store: ReviewAssignment) -> None:
    store.assign("t:1", "anna", T09)
    store.assign("t:2", "anna", T10)
    store.assign("t:3", "bob", T09)
    assert store.least_loaded(["anna", "bob"]) == "bob"  # 1 < 2
    # a candidate with zero assignments is the least loaded
    assert store.least_loaded(["anna", "bob", "carol"]) == "carol"


def test_least_loaded_tie_breaks_by_candidate_order(store: ReviewAssignment) -> None:
    store.assign("t:1", "anna", T09)
    store.assign("t:2", "bob", T09)
    # equal load (1 each) -> first candidate wins, deterministically
    assert store.least_loaded(["anna", "bob"]) == "anna"
    assert store.least_loaded(["bob", "anna"]) == "bob"


def test_idempotent_reassign_upsert(store: ReviewAssignment) -> None:
    store.assign("t:1", "anna", T09)
    store.assign("t:1", "anna", T12)  # re-assign same task -> upsert, not a new row
    assert store.load_by_assignee() == {"anna": 1}  # single row survives
    got = store.assignments_for("anna")
    assert len(got) == 1
    assert got[0].assigned_at == T12  # timestamp refreshed in place


def test_unknown_assignee_returns_empty(store: ReviewAssignment) -> None:
    store.assign("t:1", "anna", T09)
    assert store.assignments_for("nobody") == []


def test_least_loaded_empty_candidates_guard(store: ReviewAssignment) -> None:
    assert store.least_loaded([]) == ""


def test_close_excludes_from_load(store: ReviewAssignment) -> None:
    store.assign("t:1", "anna", T09)
    store.assign("t:2", "anna", T10)
    store.close("t:1")  # closed task drops out of load balancing
    assert store.load_by_assignee() == {"anna": 1}
    assert [a.task_id for a in store.assignments_for("anna")] == ["t:2"]

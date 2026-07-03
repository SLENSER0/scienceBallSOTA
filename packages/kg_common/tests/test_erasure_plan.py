"""Tests for the right-to-erasure cascade planner (§19.5 audit/privacy).

Hand-checkable: a 3-store plan splits audit_log -> anonymize, others -> delete,
sorted by store name; :func:`actions_for` filters by op; empty stores -> ().
"""

from __future__ import annotations

from kg_common.security.erasure_plan import (
    OP_ANONYMIZE,
    OP_DELETE,
    ErasureAction,
    ErasurePlan,
    actions_for,
    plan_erasure,
)


def _plan() -> ErasurePlan:
    return plan_erasure("s1", ["graph", "qdrant", "audit_log"])


def _action(plan: ErasurePlan, store: str) -> ErasureAction:
    return next(action for action in plan.actions if action.store == store)


def test_three_stores_yield_three_actions() -> None:
    assert len(_plan().actions) == 3


def test_audit_log_action_is_anonymized() -> None:
    assert _action(_plan(), "audit_log").op == OP_ANONYMIZE == "anonymize"


def test_graph_action_is_deleted() -> None:
    assert _action(_plan(), "graph").op == OP_DELETE == "delete"


def test_actions_sorted_by_store_name() -> None:
    stores = [action.store for action in _plan().actions]
    assert stores == ["audit_log", "graph", "qdrant"]


def test_actions_for_delete_excludes_audit_log() -> None:
    delete_actions = actions_for(_plan(), "delete")
    delete_stores = {action.store for action in delete_actions}
    assert "audit_log" not in delete_stores
    assert delete_stores == {"graph", "qdrant"}


def test_every_action_targets_the_subject() -> None:
    assert all(action.target == "s1" for action in _plan().actions)


def test_empty_stores_yield_no_actions() -> None:
    plan = plan_erasure("s1", [])
    assert plan.actions == ()
    assert plan.subject_id == "s1"


def test_as_dict_shape() -> None:
    payload = _plan().as_dict()
    assert payload["subject_id"] == "s1"
    assert len(payload["actions"]) == 3
    assert payload["actions"][0] == {
        "store": "audit_log",
        "target": "s1",
        "op": "anonymize",
    }


def test_custom_immutable_stores_override_default() -> None:
    plan = plan_erasure("s2", ["graph", "ledger"], immutable_stores=frozenset({"ledger"}))
    assert _action(plan, "ledger").op == "anonymize"
    assert _action(plan, "graph").op == "delete"

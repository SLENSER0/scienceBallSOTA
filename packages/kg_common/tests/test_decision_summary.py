"""Curation-decision summary (§16.13) — hand-checked pure-function tests."""

from __future__ import annotations

from kg_common.storage.decision_summary import DecisionSummary, summarize_decisions


def _row(target_id: str, action: str, actor: str, version: int) -> dict[str, object]:
    """Одна строка решения формы Decision.as_dict (только нужные для свода поля)."""
    return {"target_id": target_id, "action": action, "actor": actor, "version": version}


def test_total_counts_every_row() -> None:
    rows = [
        _row("e1", "approve", "alice", 1),
        _row("e1", "approve", "bob", 2),
        _row("e2", "reject", "alice", 1),
    ]
    s = summarize_decisions(rows)
    assert s.total == 3


def test_by_action_counts() -> None:
    rows = [
        _row("e1", "approve", "alice", 1),
        _row("e2", "approve", "bob", 1),
        _row("e3", "reject", "alice", 1),
        _row("e4", "merge", "carol", 1),
        _row("e5", "approve", "carol", 1),
    ]
    s = summarize_decisions(rows)
    # 3 approve, 1 reject, 1 merge; keys sorted alphabetically for determinism
    assert s.by_action == {"approve": 3, "merge": 1, "reject": 1}
    assert list(s.by_action) == ["approve", "merge", "reject"]


def test_by_actor_counts() -> None:
    rows = [
        _row("e1", "approve", "alice", 1),
        _row("e2", "reject", "alice", 1),
        _row("e3", "approve", "bob", 1),
        _row("e4", "merge", "alice", 1),
    ]
    s = summarize_decisions(rows)
    # alice authored 3 decisions, bob 1; keys sorted
    assert s.by_actor == {"alice": 3, "bob": 1}
    assert list(s.by_actor) == ["alice", "bob"]


def test_latest_per_target_keeps_max_version() -> None:
    rows = [
        _row("e1", "approve", "alice", 1),
        _row("e1", "approve", "bob", 3),  # highest for e1
        _row("e1", "reject", "carol", 2),  # out-of-order, must not lower the max
        _row("e2", "merge", "alice", 5),
        _row("e2", "approve", "bob", 4),
    ]
    s = summarize_decisions(rows)
    assert s.latest_per_target == {"e1": 3, "e2": 5}


def test_single_row() -> None:
    s = summarize_decisions([_row("e1", "approve", "alice", 1)])
    assert s.total == 1
    assert s.by_action == {"approve": 1}
    assert s.by_actor == {"alice": 1}
    assert s.latest_per_target == {"e1": 1}


def test_empty_is_all_zeros() -> None:
    s = summarize_decisions([])
    assert s.total == 0
    assert s.by_action == {}
    assert s.by_actor == {}
    assert s.latest_per_target == {}


def test_missing_version_treated_as_zero() -> None:
    # a partial row without a version must not crash; version defaults to 0
    rows = [
        {"target_id": "e1", "action": "approve", "actor": "alice"},
        _row("e1", "approve", "alice", 2),
    ]
    s = summarize_decisions(rows)
    assert s.total == 2
    assert s.latest_per_target == {"e1": 2}


def test_as_dict_is_a_fresh_copy() -> None:
    rows = [
        _row("e1", "approve", "alice", 1),
        _row("e1", "reject", "bob", 2),
        _row("e2", "approve", "alice", 1),
    ]
    s = summarize_decisions(rows)
    assert s.as_dict() == {
        "total": 3,
        "by_action": {"approve": 2, "reject": 1},
        "by_actor": {"alice": 2, "bob": 1},
        "latest_per_target": {"e1": 2, "e2": 1},
    }
    # as_dict returns a fresh copy: mutating it never touches the frozen instance
    dumped = s.as_dict()
    dumped["by_action"]["approve"] = 999
    assert s.by_action == {"approve": 2, "reject": 1}


def test_summary_type_and_fields() -> None:
    s = summarize_decisions([_row("e1", "approve", "alice", 1)])
    assert isinstance(s, DecisionSummary)
    # frozen dataclass: attributes are read-only
    try:
        s.total = 99  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen must reject assignment
        raise AssertionError("DecisionSummary must be frozen")

"""Decision store (§16.7): версионирование и привязка решений к изменениям графа."""

from __future__ import annotations

import pytest

from kg_common.storage.decisions import Decision, DecisionStore


@pytest.fixture
def store() -> DecisionStore:
    s = DecisionStore("sqlite:///:memory:")
    s.migrate()
    return s


def test_record_and_history_ordered_by_version(store: DecisionStore) -> None:
    store.record_decision(Decision("d1", "ent:1", action="merge", actor="alice"))
    store.record_decision(Decision("d2", "ent:1", action="correct", actor="bob"))
    store.record_decision(Decision("d3", "ent:1", action="revert", actor="alice"))
    hist = store.history_for("ent:1")
    assert [d.decision_id for d in hist] == ["d1", "d2", "d3"]
    assert [d.version for d in hist] == [1, 2, 3]


def test_version_increments_per_target(store: DecisionStore) -> None:
    d1 = store.record_decision(Decision("d1", "ent:1"))
    d2 = store.record_decision(Decision("d2", "ent:1"))
    d3 = store.record_decision(Decision("d3", "ent:1"))
    assert (d1.version, d2.version, d3.version) == (1, 2, 3)


def test_latest_for_returns_highest_version(store: DecisionStore) -> None:
    store.record_decision(Decision("d1", "ent:1"))
    store.record_decision(Decision("d2", "ent:1"))
    store.record_decision(Decision("d3", "ent:1"))
    latest = store.latest_for("ent:1")
    assert latest is not None
    assert latest.version == 3 and latest.decision_id == "d3"


def test_record_is_idempotent_by_decision_id(store: DecisionStore) -> None:
    store.record_decision(Decision("d1", "ent:1", actor="alice"))
    store.record_decision(Decision("d2", "ent:1", actor="bob"))
    # повторная запись того же id: без дубликата и без роста версии
    again = store.record_decision(Decision("d1", "ent:1", actor="alice"))
    assert again.version == 1
    assert len(store.history_for("ent:1")) == 2
    assert store.latest_for("ent:1").version == 2


def test_list_by_actor(store: DecisionStore) -> None:
    store.record_decision(Decision("d1", "ent:1", actor="alice"))
    store.record_decision(Decision("d2", "ent:2", actor="bob"))
    store.record_decision(Decision("d3", "ent:3", actor="alice"))
    alice = store.list_by_actor("alice")
    assert {d.decision_id for d in alice} == {"d1", "d3"}
    assert store.list_by_actor("carol") == []


def test_multiple_targets_independent_versioning(store: DecisionStore) -> None:
    store.record_decision(Decision("a1", "ent:A"))
    store.record_decision(Decision("b1", "ent:B"))
    store.record_decision(Decision("a2", "ent:A"))
    assert [d.version for d in store.history_for("ent:A")] == [1, 2]
    assert [d.version for d in store.history_for("ent:B")] == [1]
    assert store.latest_for("ent:A").decision_id == "a2"
    assert store.latest_for("ent:B").decision_id == "b1"


def test_empty_store_is_graceful(store: DecisionStore) -> None:
    assert store.history_for("missing") == []
    assert store.latest_for("missing") is None
    assert store.list_by_actor("nobody") == []


def test_as_dict_exposes_all_fields(store: DecisionStore) -> None:
    stored = store.record_decision(
        Decision(
            "d1",
            "ent:1",
            event_id="ev:9",
            action="merge",
            actor="alice",
            before_hash="h0",
            after_hash="h1",
        )
    )
    data = stored.as_dict()
    assert data["decision_id"] == "d1" and data["version"] == 1
    assert data["before_hash"] == "h0" and data["after_hash"] == "h1"
    assert set(data) >= {
        "decision_id",
        "target_id",
        "event_id",
        "action",
        "actor",
        "before_hash",
        "after_hash",
        "created_at",
        "version",
    }

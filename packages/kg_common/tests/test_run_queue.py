"""Tests for the queued-run admission coordinator — тесты допуска (§9.7)."""

from __future__ import annotations

import pytest

from kg_common.run_queue import AdmissionDecision, QueuedRun, admit


def test_queued_run_as_dict_and_frozen() -> None:
    run = QueuedRun("a", {"engine": "llm"})
    assert run.as_dict() == {"run_id": "a", "tags": {"engine": "llm"}}
    with pytest.raises((AttributeError, TypeError)):
        run.run_id = "b"  # type: ignore[misc]


def test_queued_run_default_tags_empty() -> None:
    run = QueuedRun("a")
    assert run.as_dict() == {"run_id": "a", "tags": {}}


def test_decision_as_dict_empty() -> None:
    assert AdmissionDecision((), ()).as_dict() == {"launch": [], "hold": []}


def test_decision_as_dict_and_frozen() -> None:
    decision = AdmissionDecision(("a", "b"), ("c",))
    assert decision.as_dict() == {"launch": ["a", "b"], "hold": ["c"]}
    with pytest.raises((AttributeError, TypeError)):
        decision.launch = ()  # type: ignore[misc]


def test_global_ceiling_fifo() -> None:
    decision = admit(
        [QueuedRun("a", {}), QueuedRun("b", {}), QueuedRun("c", {})],
        max_concurrent=2,
    )
    assert decision.launch == ("a", "b")
    assert decision.hold == ("c",)


def test_tag_limit_admits_only_first() -> None:
    decision = admit(
        [QueuedRun("a", {"engine": "llm"}), QueuedRun("b", {"engine": "llm"})],
        max_concurrent=5,
        tag_limits={("engine", "llm"): 1},
    )
    assert decision.launch == ("a",)
    assert decision.hold == ("b",)


def test_in_flight_consumes_global_slots() -> None:
    decision = admit(
        [QueuedRun("a", {})],
        in_flight=[{}, {}],
        max_concurrent=2,
    )
    assert decision.launch == ()
    assert decision.hold == ("a",)


def test_in_flight_consumes_tag_slots() -> None:
    # One engine=llm already running fills the limit of 1 — hold the queued one.
    decision = admit(
        [QueuedRun("a", {"engine": "llm"})],
        in_flight=[{"engine": "llm"}],
        max_concurrent=5,
        tag_limits={("engine", "llm"): 1},
    )
    assert decision.launch == ()
    assert decision.hold == ("a",)


def test_unlimited_tag_unaffected_by_other_limits() -> None:
    # 'a' is capped (engine=llm limit 1) but 'b' carrying engine=gpu is free.
    decision = admit(
        [
            QueuedRun("a", {"engine": "llm"}),
            QueuedRun("x", {"engine": "llm"}),
            QueuedRun("b", {"engine": "gpu"}),
        ],
        max_concurrent=5,
        tag_limits={("engine", "llm"): 1},
    )
    assert decision.launch == ("a", "b")
    assert decision.hold == ("x",)


def test_tag_limit_two_slots() -> None:
    decision = admit(
        [
            QueuedRun("a", {"engine": "llm"}),
            QueuedRun("b", {"engine": "llm"}),
            QueuedRun("c", {"engine": "llm"}),
        ],
        max_concurrent=5,
        tag_limits={("engine", "llm"): 2},
    )
    assert decision.launch == ("a", "b")
    assert decision.hold == ("c",)


def test_multiple_tags_all_must_fit() -> None:
    # 'a' needs both region=eu (limit 1) and engine=llm (limit 2); it launches
    # and consumes region=eu, so 'b' (also region=eu) is held despite llm slack.
    decision = admit(
        [
            QueuedRun("a", {"region": "eu", "engine": "llm"}),
            QueuedRun("b", {"region": "eu", "engine": "llm"}),
        ],
        max_concurrent=5,
        tag_limits={("region", "eu"): 1, ("engine", "llm"): 2},
    )
    assert decision.launch == ("a",)
    assert decision.hold == ("b",)


def test_partition_covers_every_run_once_and_in_order() -> None:
    runs = [
        QueuedRun("a", {"engine": "llm"}),
        QueuedRun("b", {}),
        QueuedRun("c", {"engine": "llm"}),
        QueuedRun("d", {}),
    ]
    decision = admit(runs, max_concurrent=2, tag_limits={("engine", "llm"): 1})
    combined = list(decision.launch) + list(decision.hold)
    assert sorted(combined) == ["a", "b", "c", "d"]
    assert len(combined) == len(set(combined)) == 4
    # Order preserved within each partition (FIFO).
    ids = [r.run_id for r in runs]
    assert [i for i in ids if i in decision.launch] == list(decision.launch)
    assert [i for i in ids if i in decision.hold] == list(decision.hold)


def test_empty_queue() -> None:
    decision = admit([], max_concurrent=2)
    assert decision.launch == ()
    assert decision.hold == ()


def test_launch_preserves_queue_order() -> None:
    runs = [QueuedRun(x, {}) for x in ("z", "y", "x", "w")]
    decision = admit(runs, max_concurrent=3)
    assert decision.launch == ("z", "y", "x")
    assert decision.hold == ("w",)

"""Tests for §16.7 decision traceability (value → event → decision → actor → evidence)."""

from __future__ import annotations

from kg_common.storage.decision_trace import TraceLink, build_trace, latest_actor


def _events() -> list[dict]:
    """Two events for entity 'e1': ev1 (earlier, in a decision), ev2 (later, orphan)."""
    return [
        {
            "event_id": "ev2",
            "target_id": "e1",
            "actor": "bob",
            "evidence_ids": ["s3"],
            "created_at": "2026-07-02T10:00:00",
        },
        {
            "event_id": "ev1",
            "target_id": "e1",
            "actor": "alice",
            "evidence_ids": ["s1", "s2"],
            "created_at": "2026-07-01T09:00:00",
        },
        {
            "event_id": "ev9",
            "target_id": "other",
            "actor": "zed",
            "evidence_ids": ["z1"],
            "created_at": "2026-07-01T00:00:00",
        },
    ]


def _decisions() -> list[dict]:
    """Decision d1 INCLUDES ev1 only (ev2 stays orphan)."""
    return [{"decision_id": "d1", "curation_event_ids": ["ev1"]}]


def test_two_events_one_in_decision_one_orphan() -> None:
    links = build_trace("e1", _events(), _decisions())
    assert len(links) == 2
    by_event = {link.event_id: link for link in links}
    assert by_event["ev1"].decision_id == "d1"
    assert by_event["ev2"].decision_id == ""


def test_links_ordered_by_created_at_ascending() -> None:
    links = build_trace("e1", _events(), _decisions())
    assert [link.event_id for link in links] == ["ev1", "ev2"]


def test_evidence_ids_preserved_per_link() -> None:
    links = build_trace("e1", _events(), _decisions())
    by_event = {link.event_id: link for link in links}
    assert by_event["ev1"].evidence_ids == ["s1", "s2"]
    assert by_event["ev2"].evidence_ids == ["s3"]


def test_latest_actor_is_newest_event_actor() -> None:
    links = build_trace("e1", _events(), _decisions())
    # ev2 (bob) is newest by created_at.
    assert latest_actor(links) == "bob"


def test_empty_inputs() -> None:
    assert build_trace("x", [], []) == []
    assert latest_actor([]) is None


def test_decision_including_two_events_shares_decision_id() -> None:
    events = [
        {
            "event_id": "a",
            "target_id": "e1",
            "actor": "alice",
            "evidence_ids": [],
            "created_at": "2026-01-01",
        },
        {
            "event_id": "b",
            "target_id": "e1",
            "actor": "bob",
            "evidence_ids": [],
            "created_at": "2026-01-02",
        },
    ]
    decisions = [{"decision_id": "d7", "curation_event_ids": ["a", "b"]}]
    links = build_trace("e1", events, decisions)
    assert len(links) == 2
    assert {link.decision_id for link in links} == {"d7"}


def test_as_dict_keys_include_evidence_ids() -> None:
    link = TraceLink(
        entity_id="e1",
        event_id="ev1",
        decision_id="d1",
        actor="alice",
        evidence_ids=["s1"],
    )
    d = link.as_dict()
    assert "evidence_ids" in d
    assert set(d) == {"entity_id", "event_id", "decision_id", "actor", "evidence_ids"}
    assert d["evidence_ids"] == ["s1"]

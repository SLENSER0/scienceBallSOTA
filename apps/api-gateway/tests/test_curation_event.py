"""Тесты канонического строителя :class:`CurationEvent` §12.3 (§14.14).

Ручной контроль: валидируем глагол действия, автозаполнение id/времени, набор
полей ``as_dict`` и значения по умолчанию. Real, hand-checkable assertions for
the §12.3 curation-event builder.
"""

from __future__ import annotations

import pytest
from api_gateway.curation_event import (
    VALID_ACTIONS,
    CurationEvent,
    build_event,
)

# Десять канонических имён полей §12.3 — the ten §12.3 field names.
_EXPECTED_FIELDS = {
    "event_id",
    "actor_id",
    "action",
    "target_type",
    "target_id",
    "before",
    "after",
    "reason",
    "created_at",
    "request_id",
}


def test_action_roundtrips() -> None:
    assert build_event("u1", "merge", "Entity", "e1").action == "merge"


def test_bogus_action_raises() -> None:
    with pytest.raises(ValueError):
        build_event("u1", "bogus", "Entity", "e1")


def test_gap_annotate_in_valid_actions() -> None:
    assert "gap_annotate" in VALID_ACTIONS


def test_valid_actions_full_set() -> None:
    assert (
        frozenset(
            {
                "merge",
                "split",
                "alias_add",
                "accept",
                "reject",
                "correct",
                "schema_change",
                "mark_inferred",
                "manual_evidence",
                "gap_annotate",
                "experiment_verify",
            }
        )
        == VALID_ACTIONS
    )


def test_before_after_default_empty() -> None:
    event = build_event("u1", "merge", "Entity", "e1")
    assert event.before == {}
    assert event.after == {}


def test_explicit_id_and_timestamp_preserved() -> None:
    event = build_event("u1", "split", "Entity", "e1", event_id="x", created_at="t")
    assert event.event_id == "x"
    assert event.created_at == "t"


def test_autofilled_event_id_non_empty() -> None:
    assert len(build_event("u1", "merge", "Entity", "e1").event_id) > 0


def test_autofilled_created_at_non_empty() -> None:
    assert len(build_event("u1", "merge", "Entity", "e1").created_at) > 0


def test_reason_defaults_blank() -> None:
    assert build_event("u1", "merge", "Entity", "e1").reason == ""


def test_request_id_defaults_none() -> None:
    assert build_event("u1", "merge", "Entity", "e1").request_id is None


def test_as_dict_keys_are_the_ten_fields() -> None:
    keys = set(build_event("u1", "merge", "Entity", "e1").as_dict().keys())
    assert keys == _EXPECTED_FIELDS
    assert len(_EXPECTED_FIELDS) == 10


def test_as_dict_values_match_attributes() -> None:
    event = build_event(
        "u1",
        "correct",
        "Entity",
        "e1",
        before={"name": "old"},
        after={"name": "new"},
        reason="typo",
        request_id="req-9",
        event_id="ev-1",
        created_at="2026-07-03T00:00:00+00:00",
    )
    assert event.as_dict() == {
        "event_id": "ev-1",
        "actor_id": "u1",
        "action": "correct",
        "target_type": "Entity",
        "target_id": "e1",
        "before": {"name": "old"},
        "after": {"name": "new"},
        "reason": "typo",
        "created_at": "2026-07-03T00:00:00+00:00",
        "request_id": "req-9",
    }


def test_before_after_are_copied() -> None:
    src = {"k": "v"}
    event = build_event("u1", "merge", "Entity", "e1", before=src)
    src["k"] = "mutated"
    assert event.before == {"k": "v"}


def test_event_is_frozen() -> None:
    event = build_event("u1", "merge", "Entity", "e1")
    with pytest.raises((AttributeError, TypeError)):
        event.action = "split"  # type: ignore[misc]


def test_autofilled_ids_are_unique() -> None:
    a = build_event("u1", "merge", "Entity", "e1").event_id
    b = build_event("u1", "merge", "Entity", "e1").event_id
    assert a != b


def test_direct_construction_defaults() -> None:
    event = CurationEvent(
        event_id="ev",
        actor_id="u1",
        action="accept",
        target_type="Entity",
        target_id="e1",
    )
    assert event.before == {}
    assert event.after == {}
    assert event.reason == ""
    assert event.created_at == ""
    assert event.request_id is None

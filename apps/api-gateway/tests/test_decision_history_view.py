"""Тесты просмотрщика истории решений с диффом before/after (§5.2.8, §12.3).

Hand-checkable tests for :mod:`api_gateway.decision_history_view`: empty input,
the three diff kinds (changed / added / removed), missing-snapshot handling,
descending sort by ``created_at`` with stable ties, the ``target_ref`` shape,
unchanged-key omission, ``total`` and JSON-serialisability of ``as_dict()``.
"""

from __future__ import annotations

import json

from api_gateway.decision_history_view import (
    DecisionHistoryView,
    build_decision_history,
    compute_diff,
)


def _event(**overrides: object) -> dict[str, object]:
    """Собрать §12.3 CurationEvent со значениями по умолчанию / build an event."""
    base: dict[str, object] = {
        "action": "correct",
        "actor": "curator-1",
        "target_type": "entity",
        "target_id": "e1",
        "before": {},
        "after": {},
        "reason": "fix",
        "created_at": "2020-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_empty_input_yields_no_entries() -> None:
    """Пустой вход → entries==() и total==0 / empty input is empty view."""
    view = build_decision_history([])
    assert view.entries == ()
    assert view.total == 0
    assert view.as_dict() == {"entries": [], "total": 0}


def test_changed_value_produces_changed_diff() -> None:
    """before/after с разным значением → changed / value change is 'changed'."""
    events = [_event(before={"unit": "MPa"}, after={"unit": "GPa"})]
    view = build_decision_history(events)
    diff = view.entries[0]["diff"]
    assert diff["changed"] == {"unit": {"from": "MPa", "to": "GPa"}}
    assert diff["added"] == {}
    assert diff["removed"] == {}


def test_missing_before_treats_all_after_as_added() -> None:
    """before None → все ключи after в added / missing before is all-added."""
    events = [_event(before=None, after={"alias": "x"})]
    diff = build_decision_history(events).entries[0]["diff"]
    assert diff["added"] == {"alias": "x"}
    assert diff["removed"] == {}
    assert diff["changed"] == {}


def test_missing_after_treats_all_before_as_removed() -> None:
    """after None → все ключи before в removed / missing after is all-removed."""
    events = [_event(before={"x": 1}, after=None)]
    diff = build_decision_history(events).entries[0]["diff"]
    assert diff["removed"] == {"x": 1}
    assert diff["added"] == {}
    assert diff["changed"] == {}


def test_unchanged_keys_appear_in_no_group() -> None:
    """Неизменённый ключ не попадает никуда / unchanged key is omitted."""
    diff = compute_diff({"unit": "MPa", "n": 1}, {"unit": "MPa", "n": 2})
    assert "unit" not in diff["added"]
    assert "unit" not in diff["removed"]
    assert "unit" not in diff["changed"]
    assert diff["changed"] == {"n": {"from": 1, "to": 2}}


def test_entries_sorted_by_created_at_descending() -> None:
    """Новейшее событие первым / 2021 sorts before 2020."""
    old = _event(created_at="2020-06-01T00:00:00Z", target_id="old")
    new = _event(created_at="2021-06-01T00:00:00Z", target_id="new")
    view = build_decision_history([old, new])
    assert view.entries[0]["target_id"] == "new"
    assert view.entries[1]["target_id"] == "old"


def test_equal_created_at_ties_are_stable() -> None:
    """Равная дата → исходный порядок сохраняется / stable ties."""
    a = _event(created_at="2022-01-01T00:00:00Z", target_id="a")
    b = _event(created_at="2022-01-01T00:00:00Z", target_id="b")
    view = build_decision_history([a, b])
    assert [e["target_id"] for e in view.entries] == ["a", "b"]


def test_target_ref_shape() -> None:
    """target_ref == {type, id} из полей события / target_ref mirrors target."""
    events = [_event(target_type="property", target_id="p9")]
    entry = build_decision_history(events).entries[0]
    assert entry["target_ref"] == {"type": "property", "id": "p9"}


def test_total_equals_event_count() -> None:
    """total == len(events) / total counts inputs."""
    events = [_event(created_at=f"2020-01-0{i}T00:00:00Z") for i in range(1, 4)]
    view = build_decision_history(events)
    assert view.total == 3
    assert len(view.entries) == 3


def test_as_dict_is_json_serialisable() -> None:
    """as_dict() сериализуется в JSON / payload round-trips through json."""
    events = [_event(before={"unit": "MPa"}, after={"unit": "GPa", "alias": "y"})]
    payload = build_decision_history(events).as_dict()
    restored = json.loads(json.dumps(payload))
    assert restored["total"] == 1
    assert restored["entries"][0]["diff"]["changed"]["unit"] == {"from": "MPa", "to": "GPa"}
    assert restored["entries"][0]["diff"]["added"] == {"alias": "y"}


def test_view_is_frozen_dataclass() -> None:
    """DecisionHistoryView неизменяем / frozen instance rejects mutation."""
    view = DecisionHistoryView(entries=(), total=0)
    try:
        view.total = 5  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must raise
        raise AssertionError("expected frozen dataclass to reject assignment")

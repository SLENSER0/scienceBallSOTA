"""Before/after diff of a curation event (§16.8): field-level property diff.

Hand-checked: added/removed/changed detection, old→new capture, unchanged
listing, a nested-value change surfacing as a top-level changed key, is_noop on
identical maps, a bilingual summary that names the changed field, and as_dict.
"""

from __future__ import annotations

from kg_common.storage.curation_diff import (
    CurationDiff,
    diff_states,
    is_noop,
    summarize_diff,
)


def test_added_field_detected() -> None:
    diff = diff_states({"name": "Ca"}, {"name": "Ca", "charge": 2})
    assert diff.added == {"charge": 2}
    assert diff.removed == {}
    assert diff.changed == {}
    assert diff.unchanged_keys == ["name"]


def test_removed_field_detected() -> None:
    diff = diff_states({"name": "Ca", "charge": 2}, {"name": "Ca"})
    assert diff.removed == {"charge": 2}  # ключ → старое значение
    assert diff.added == {}
    assert diff.changed == {}
    assert diff.unchanged_keys == ["name"]


def test_changed_value_old_to_new_captured() -> None:
    diff = diff_states({"status": "draft"}, {"status": "approved"})
    # changed отображает ключ → (старое, новое).
    assert diff.changed == {"status": ("draft", "approved")}
    assert diff.added == {} and diff.removed == {}
    assert diff.unchanged_keys == []


def test_unchanged_listed() -> None:
    before = {"a": 1, "b": 2, "c": 3}
    after = {"a": 1, "b": 99, "c": 3}
    diff = diff_states(before, after)
    # b изменился; a и c остались — в отсортированном списке.
    assert diff.unchanged_keys == ["a", "c"]
    assert diff.changed == {"b": (2, 99)}


def test_nested_value_change() -> None:
    before = {"meta": {"unit": "kJ/mol"}}
    after = {"meta": {"unit": "eV"}}
    diff = diff_states(before, after)
    # Плоский по верхним ключам: вложенный dict меняется целиком.
    assert diff.changed == {"meta": ({"unit": "kJ/mol"}, {"unit": "eV"})}
    assert diff.unchanged_keys == []
    assert not is_noop(diff)


def test_is_noop_on_identical() -> None:
    state = {"name": "Ca", "charge": 2, "meta": {"k": "v"}}
    diff = diff_states(state, dict(state))
    assert is_noop(diff) is True
    assert diff.added == {} and diff.removed == {} and diff.changed == {}
    # Все ключи — без изменений (отсортированы).
    assert diff.unchanged_keys == ["charge", "meta", "name"]


def test_is_noop_false_when_any_change() -> None:
    assert is_noop(diff_states({"x": 1}, {"x": 2})) is False  # changed
    assert is_noop(diff_states({}, {"x": 1})) is False  # added
    assert is_noop(diff_states({"x": 1}, {})) is False  # removed


def test_summarize_mentions_changed_field() -> None:
    diff = diff_states({"status": "draft"}, {"status": "approved"})
    summary = summarize_diff(diff)
    # Имя изменённого поля и оба значения присутствуют в сводке.
    assert "status" in summary
    assert "draft" in summary and "approved" in summary
    assert "~1 изм/changed" in summary


def test_summarize_counts_all_sections() -> None:
    before = {"keep": 1, "drop": 2, "mut": "old"}
    after = {"keep": 1, "mut": "new", "fresh": 9}
    summary = summarize_diff(diff_states(before, after))
    # +1 added (fresh), -1 removed (drop), ~1 changed (mut), =1 unchanged (keep).
    assert "+1 доб/added" in summary
    assert "-1 удал/removed" in summary
    assert "~1 изм/changed" in summary
    assert "=1 без-изм/unchanged" in summary
    assert "fresh" in summary and "drop" in summary and "mut" in summary


def test_summarize_noop_has_zero_counts() -> None:
    summary = summarize_diff(diff_states({"a": 1}, {"a": 1}))
    assert summary == (
        "Диф/Diff: +0 доб/added / -0 удал/removed / ~0 изм/changed / =1 без-изм/unchanged"
    )


def test_as_dict() -> None:
    before = {"name": "Ca", "charge": 2, "note": "x"}
    after = {"name": "Calcium", "charge": 2, "extra": True}
    data = diff_states(before, after).as_dict()
    assert data == {
        "added": {"extra": True},
        "removed": {"note": "x"},
        "changed": {"name": ("Ca", "Calcium")},
        "unchanged_keys": ["charge"],
    }
    assert set(data) == {"added", "removed", "changed", "unchanged_keys"}


def test_curation_diff_is_frozen() -> None:
    diff = diff_states({"a": 1}, {"a": 2})
    assert isinstance(diff, CurationDiff)
    try:
        diff.added = {}  # type: ignore[misc]
    except Exception as exc:  # frozen dataclass → FrozenInstanceError
        assert type(exc).__name__ == "FrozenInstanceError"
    else:  # pragma: no cover - защита от регресса заморозки
        raise AssertionError("CurationDiff must be frozen")

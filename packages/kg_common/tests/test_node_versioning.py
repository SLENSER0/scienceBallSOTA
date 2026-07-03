"""Тесты версионирования узлов — node lifecycle transitions (§16.7)."""

from __future__ import annotations

from kg_common.storage.node_versioning import (
    VersionTransition,
    bump_version,
    is_current,
)

_NOW = "2026-01-01T00:00:00Z"


def _base_node() -> dict[str, object]:
    return {"id": "n", "version": 1, "v": 1, "valid_to": None}


def test_new_version_incremented() -> None:
    t = bump_version(_base_node(), {"v": 2}, _NOW)
    assert t.new["version"] == 2


def test_old_valid_to_stamped() -> None:
    t = bump_version(_base_node(), {"v": 2}, _NOW)
    assert t.old["valid_to"] == _NOW


def test_new_window_opened() -> None:
    t = bump_version(_base_node(), {"v": 2}, _NOW)
    assert t.new["valid_from"] == _NOW
    assert t.new["valid_to"] is None


def test_new_id_sets_superseded_by() -> None:
    t = bump_version(_base_node(), {"v": 2}, _NOW, new_id="n2")
    assert t.old["superseded_by"] == "n2"
    assert t.new["superseded_by"] is None


def test_no_new_id_leaves_old_superseded_by_absent() -> None:
    t = bump_version(_base_node(), {"v": 2}, _NOW)
    assert "superseded_by" not in t.old
    assert t.new["superseded_by"] is None


def test_changes_applied_only_to_new() -> None:
    t = bump_version(_base_node(), {"v": 2}, _NOW)
    assert t.old["v"] == 1
    assert t.new["v"] == 2


def test_is_current() -> None:
    t = bump_version(_base_node(), {"v": 2}, _NOW)
    assert is_current(t.old) is False
    assert is_current(t.new) is True


def test_missing_version_defaults_to_two() -> None:
    node = {"id": "n", "v": 1, "valid_to": None}
    t = bump_version(node, {"v": 2}, _NOW)
    assert t.new["version"] == 2


def test_as_dict_has_old_and_new() -> None:
    t = bump_version(_base_node(), {"v": 2}, _NOW)
    d = t.as_dict()
    assert "old" in d
    assert "new" in d


def test_as_dict_is_copy() -> None:
    t = bump_version(_base_node(), {"v": 2}, _NOW)
    d = t.as_dict()
    d["old"]["v"] = 999
    assert t.old["v"] == 1


def test_source_node_not_mutated() -> None:
    node = _base_node()
    bump_version(node, {"v": 2}, _NOW)
    assert node["valid_to"] is None
    assert node["v"] == 1
    assert "superseded_by" not in node


def test_transition_is_frozen() -> None:
    t = VersionTransition(old={}, new={})
    try:
        t.old = {"x": 1}  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("VersionTransition should be frozen")

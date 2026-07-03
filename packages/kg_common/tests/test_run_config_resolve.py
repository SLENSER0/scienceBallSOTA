"""Tests for run config resolution — тесты разрешения конфигурации (§9.7/§9.9)."""

from __future__ import annotations

from kg_common.run_config_resolve import ResolvedConfig, get_path, resolve_config


def test_scalar_override_wins() -> None:
    assert resolve_config({"a": 1}, {"a": 2}).as_dict() == {"a": 2}


def test_dict_merge_is_recursive() -> None:
    assert resolve_config({"x": {"y": 1}}, {"x": {"z": 2}}).as_dict() == {"x": {"y": 1, "z": 2}}


def test_list_is_replaced_not_merged() -> None:
    assert resolve_config({"k": [1, 2]}, {"k": [9]}).as_dict() == {"k": [9]}


def test_get_path_nested_hit() -> None:
    assert get_path(resolve_config({"x": {"y": {"z": 7}}}), "x.y.z") == 7


def test_get_path_missing_returns_default() -> None:
    assert get_path(resolve_config({"a": 1}), "a.b.c", "d") == "d"


def test_as_dict_deep_copy_isolation() -> None:
    cfg = resolve_config({"x": {"y": 1}})
    first = cfg.as_dict()
    first["x"]["y"] = 999
    first["x"]["new"] = "leak"
    second = cfg.as_dict()
    assert second == {"x": {"y": 1}}


def test_multiple_overlapping_overrides() -> None:
    resolved = resolve_config({"a": 1, "b": 2}, {"b": 3}, {"a": 9})
    assert resolved.as_dict() == {"a": 9, "b": 3}


def test_inputs_are_not_mutated() -> None:
    defaults = {"x": {"y": 1}}
    override = {"x": {"z": 2}}
    resolve_config(defaults, override)
    assert defaults == {"x": {"y": 1}}
    assert override == {"x": {"z": 2}}


def test_deep_nested_three_level_merge() -> None:
    resolved = resolve_config({"a": {"b": {"c": 1, "keep": 0}}}, {"a": {"b": {"c": 2}}})
    assert resolved.as_dict() == {"a": {"b": {"c": 2, "keep": 0}}}


def test_later_override_dict_replaces_scalar() -> None:
    # base scalar under a key becomes a dict when the override provides a dict
    resolved = resolve_config({"a": 1}, {"a": {"b": 2}})
    assert resolved.as_dict() == {"a": {"b": 2}}


def test_get_path_single_segment() -> None:
    assert get_path(resolve_config({"a": 1}), "a") == 1


def test_get_path_stops_on_non_dict() -> None:
    # traversing past a scalar returns the default rather than raising
    assert get_path(resolve_config({"a": 5}), "a.b", "fallback") == "fallback"


def test_nested_override_dict_is_deep_copied() -> None:
    # a nested dict introduced purely by an override must not alias the input
    override = {"x": {"y": {"deep": 1}}}
    resolved = resolve_config({}, override)
    resolved.as_dict()["x"]["y"]["deep"] = 42
    assert override == {"x": {"y": {"deep": 1}}}
    assert resolved.as_dict() == {"x": {"y": {"deep": 1}}}


def test_resolved_config_is_frozen() -> None:
    cfg = ResolvedConfig(data={"a": 1})
    import dataclasses

    try:
        cfg.data = {"b": 2}  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("ResolvedConfig must be frozen")


def test_no_overrides_returns_defaults_copy() -> None:
    defaults = {"a": {"b": 1}}
    resolved = resolve_config(defaults)
    resolved.as_dict()["a"]["b"] = 99
    assert defaults == {"a": {"b": 1}}

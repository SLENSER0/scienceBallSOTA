"""Tests for the JSON depth / size / node-count guard (§14.2 / §14.12).

Hermetic and dependency-free. :func:`json_depth` and :func:`count_nodes` are
checked on hand-countable literals (including scalars and empty containers);
:func:`enforce_json_limits` is exercised on each of its three failure modes
(byte cap, depth cap, node cap) and on the passing path; the frozen
:class:`JsonLimits` budget is checked for immutability and :meth:`as_dict`.
"""

from __future__ import annotations

import dataclasses

import pytest
from api_gateway.json_guard import (
    JsonLimits,
    JsonTooDeep,
    JsonTooLarge,
    count_nodes,
    enforce_json_limits,
    json_depth,
)


def test_json_depth_scalar_is_zero() -> None:
    assert json_depth(5) == 0
    assert json_depth("x") == 0
    assert json_depth(None) == 0
    assert json_depth(True) == 0


def test_json_depth_nested_dict() -> None:
    assert json_depth({"a": {"b": 1}}) == 2


def test_json_depth_nested_list() -> None:
    assert json_depth([1, [2, [3]]]) == 3


def test_json_depth_flat_container_is_one() -> None:
    assert json_depth({"a": 1, "b": 2}) == 1
    assert json_depth([1, 2, 3]) == 1


def test_json_depth_empty_container_is_one() -> None:
    assert json_depth({}) == 1
    assert json_depth([]) == 1


def test_json_depth_mixed_nesting_takes_max_branch() -> None:
    # shallow key "a" (depth 1), deep key "b" (list->dict, depth 2) -> 1+2 = 3
    assert json_depth({"a": 1, "b": [{"c": 2}]}) == 3


def test_count_nodes_flat_list() -> None:
    # list itself + three scalar ints
    assert count_nodes([1, 2, 3]) == 4


def test_count_nodes_scalar_is_one() -> None:
    assert count_nodes(7) == 1


def test_count_nodes_nested() -> None:
    # outer dict(1) + key "a" list(1) + two ints(2) = 4
    assert count_nodes({"a": [1, 2]}) == 4


def test_count_nodes_empty_containers() -> None:
    assert count_nodes({}) == 1
    assert count_nodes([]) == 1
    # outer dict + two empty children
    assert count_nodes({"a": {}, "b": []}) == 3


def test_enforce_raises_too_deep() -> None:
    with pytest.raises(JsonTooDeep):
        enforce_json_limits({"a": {"b": {"c": 1}}}, 10, JsonLimits(1000, 2, 999))


def test_enforce_raises_too_large() -> None:
    with pytest.raises(JsonTooLarge):
        enforce_json_limits({"a": 1}, 5000, JsonLimits(1000, 10, 999))


def test_enforce_raises_value_error_on_node_overflow() -> None:
    with pytest.raises(ValueError):
        enforce_json_limits([1, 2, 3, 4], 10, JsonLimits(1000, 10, 2))


def test_enforce_passes_within_budget() -> None:
    assert enforce_json_limits({"a": 1}, 10, JsonLimits(1000, 10, 999)) is None


def test_enforce_byte_check_precedes_structure() -> None:
    # deep + oversized: byte cap is checked first, so JsonTooLarge wins.
    with pytest.raises(JsonTooLarge):
        enforce_json_limits({"a": {"b": {"c": 1}}}, 5000, JsonLimits(1000, 1, 1))


def test_json_too_deep_and_large_are_value_errors() -> None:
    assert issubclass(JsonTooDeep, ValueError)
    assert issubclass(JsonTooLarge, ValueError)


def test_limits_as_dict() -> None:
    assert JsonLimits(1, 2, 3).as_dict()["max_depth"] == 2
    assert JsonLimits(1, 2, 3).as_dict() == {"max_bytes": 1, "max_depth": 2, "max_nodes": 3}


def test_limits_is_frozen() -> None:
    limits = JsonLimits(1, 2, 3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        limits.max_depth = 9  # type: ignore[misc]

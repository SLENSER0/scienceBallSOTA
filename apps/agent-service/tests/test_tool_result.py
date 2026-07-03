"""Hand-checked tests for §13.13 tool-result envelope.

Pure-python, no store / no LLM: build :class:`ToolResult` envelopes directly and
assert the exact shape, the success/failure split, the ``data_ref`` truncation
marker and the ``from_dict``/``as_dict`` round-trip. Every expected value is spelled
out so the test is verifiable by hand.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from agent_service.tool_result import (
    ToolResult,
    error_result,
    ok_result,
    truncate_data,
)


# ---------------------------------------------------------------------------
# ok_result / error_result: the two constructors
# ---------------------------------------------------------------------------
def test_ok_result_shape() -> None:
    r = ok_result("graph_search", {"nodes": [1, 2]}, "нашлось 2 узла / found 2 nodes")
    assert r.tool == "graph_search"
    assert r.ok is True
    assert r.data == {"nodes": [1, 2]}
    assert r.error is None
    assert r.summary == "нашлось 2 узла / found 2 nodes"
    assert r.data_ref is None


def test_error_result_ok_false() -> None:
    r = error_result("numeric_filter", "нет единицы / missing unit")
    assert r.ok is False
    assert r.tool == "numeric_filter"
    assert r.error == "нет единицы / missing unit"


def test_error_result_has_no_data() -> None:
    # An error envelope never carries a payload — only the reason for the failure.
    r = error_result("evidence_lookup", "boom")
    assert r.data is None
    assert r.data_ref is None


def test_summary_present_on_both_kinds() -> None:
    ok = ok_result("t", [], "готово / done")
    err = error_result("t", "сбой / failure")
    assert ok.summary == "готово / done"
    # the error message is echoed into summary so it is never empty.
    assert err.summary == "сбой / failure"
    assert err.summary != ""


def test_data_ref_optional_defaults_none() -> None:
    r = ok_result("t", {"x": 1}, "s")
    assert r.data_ref is None


def test_defaults_on_bare_construction() -> None:
    # Only tool/ok are required; data/error/summary/data_ref default to None/"".
    r = ToolResult(tool="t", ok=True)
    assert r.data is None
    assert r.error is None
    assert r.summary == ""
    assert r.data_ref is None


# ---------------------------------------------------------------------------
# as_dict / from_dict: serialisation round-trip
# ---------------------------------------------------------------------------
def test_as_dict_exact_shape() -> None:
    r = ok_result("graph_search", {"n": 1}, "ok")
    assert r.as_dict() == {
        "tool": "graph_search",
        "ok": True,
        "data": {"n": 1},
        "error": None,
        "summary": "ok",
        "data_ref": None,
    }


def test_from_dict_as_dict_round_trip() -> None:
    r = ToolResult(
        tool="compare_practice",
        ok=True,
        data=[{"id": "a"}, {"id": "b"}],
        error=None,
        summary="две группы / two groups",
        data_ref="truncated:5",
    )
    assert ToolResult.from_dict(r.as_dict()) == r


def test_from_dict_round_trip_for_error() -> None:
    r = error_result("gap_check", "нет данных / no data")
    assert ToolResult.from_dict(r.as_dict()) == r


def test_from_dict_tolerates_missing_optional_keys() -> None:
    r = ToolResult.from_dict({"tool": "t", "ok": True})
    assert r == ToolResult(tool="t", ok=True)
    assert r.data is None
    assert r.summary == ""


# ---------------------------------------------------------------------------
# truncate_data: cap oversized list payloads for the context window
# ---------------------------------------------------------------------------
def test_truncate_caps_list_data() -> None:
    r = ok_result("graph_search", [1, 2, 3, 4, 5], "5 items")
    capped = truncate_data(r, 3)
    assert capped.data == [1, 2, 3]
    assert capped.data_ref == "truncated:5"
    # the original envelope is untouched (frozen → a new object is returned).
    assert r.data == [1, 2, 3, 4, 5]
    assert r.data_ref is None


def test_truncate_noop_when_within_cap() -> None:
    r = ok_result("t", [1, 2], "2 items")
    assert truncate_data(r, 5) is r  # unchanged — same object returned


def test_truncate_noop_when_data_not_list() -> None:
    # data is a dict (not a bare list) → left exactly as-is.
    r = ok_result("t", {"k": [1, 2, 3]}, "dict data")
    assert truncate_data(r, 1) is r


def test_truncate_zero_yields_empty_list() -> None:
    r = ok_result("t", [1, 2, 3], "three")
    capped = truncate_data(r, 0)
    assert capped.data == []
    assert capped.data_ref == "truncated:3"


def test_truncate_negative_cap_clamped_to_zero() -> None:
    r = ok_result("t", [1, 2, 3], "three")
    capped = truncate_data(r, -4)
    assert capped.data == []
    assert capped.data_ref == "truncated:3"


# ---------------------------------------------------------------------------
# frozen: envelopes are immutable
# ---------------------------------------------------------------------------
def test_frozen_is_immutable() -> None:
    r = ok_result("t", [1], "s")
    with pytest.raises(FrozenInstanceError):
        r.ok = False  # type: ignore[misc]

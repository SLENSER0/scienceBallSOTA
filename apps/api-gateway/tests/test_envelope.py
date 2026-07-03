"""Tests for API response envelope helpers (§14.13).

Hermetic and dependency-free. Every assertion is a concrete hand-checkable
value: ``ok_envelope`` wraps a payload under ``data``; ``meta``/``request_id``
default to ``None`` yet are always present; the list variant carries ``items``
and ``total`` (including the empty-list / zero-total case); ``with_request_id``
threads an id into an existing body without mutating it; and the ``{data, meta,
request_id}`` key set stays stable across both builders.
"""

from __future__ import annotations

from api_gateway.envelope import list_envelope, ok_envelope, with_request_id


def test_ok_envelope_wraps_data() -> None:
    env = ok_envelope({"x": 1, "y": 2})
    assert env["data"] == {"x": 1, "y": 2}


def test_ok_envelope_shape_is_stable() -> None:
    # All three keys are present even with nothing but the payload supplied.
    assert set(ok_envelope("payload").keys()) == {"data", "meta", "request_id"}


def test_ok_envelope_meta_optional_defaults_to_none() -> None:
    assert ok_envelope(123)["meta"] is None


def test_ok_envelope_carries_meta_when_given() -> None:
    env = ok_envelope([1, 2], meta={"took_ms": 5})
    assert env["meta"] == {"took_ms": 5}


def test_ok_envelope_request_id_threaded() -> None:
    assert ok_envelope("ok", request_id="req-42")["request_id"] == "req-42"


def test_ok_envelope_request_id_defaults_to_none() -> None:
    assert ok_envelope("ok")["request_id"] is None


def test_list_envelope_carries_total_and_items() -> None:
    env = list_envelope(["a", "b", "c"], total=57)
    assert env["data"]["items"] == ["a", "b", "c"]
    assert env["data"]["total"] == 57


def test_list_envelope_total_independent_of_page_size() -> None:
    # total is the full count (57), not len(items) which is only the page (3).
    env = list_envelope(["a", "b", "c"], total=57)
    assert env["data"]["total"] == 57
    assert len(env["data"]["items"]) == 3


def test_list_envelope_empty_list() -> None:
    env = list_envelope([], total=0)
    assert env["data"]["items"] == []
    assert env["data"]["total"] == 0


def test_list_envelope_request_id_threaded() -> None:
    assert list_envelope([1], total=1, request_id="req-9")["request_id"] == "req-9"


def test_list_envelope_shape_is_stable() -> None:
    env = list_envelope([1, 2], total=2)
    assert set(env.keys()) == {"data", "meta", "request_id"}
    assert set(env["data"].keys()) == {"items", "total"}


def test_with_request_id_adds_id() -> None:
    body = {"data": "hi", "meta": None, "request_id": None}
    assert with_request_id(body, "req-7")["request_id"] == "req-7"


def test_with_request_id_overwrites_existing() -> None:
    body = {"data": 1, "meta": None, "request_id": "old"}
    assert with_request_id(body, "new")["request_id"] == "new"


def test_with_request_id_preserves_other_keys() -> None:
    body = {"data": {"k": "v"}, "meta": {"m": 1}, "request_id": None}
    out = with_request_id(body, "rid")
    assert out["data"] == {"k": "v"}
    assert out["meta"] == {"m": 1}


def test_with_request_id_does_not_mutate_input() -> None:
    body = {"data": 1, "meta": None, "request_id": None}
    with_request_id(body, "rid")
    assert body["request_id"] is None

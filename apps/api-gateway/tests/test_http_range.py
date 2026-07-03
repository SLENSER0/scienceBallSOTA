"""Tests for §14.9 Range/206 partial download parsing (:mod:`http_range`).

Ручные проверки разбора заголовка ``Range`` и рендера ``Content-Range``.
"""

from __future__ import annotations

from api_gateway.http_range import (
    ByteRange,
    content_range_header,
    is_satisfiable,
    parse_range,
)


def test_closed_range_length() -> None:
    """``bytes=0-99`` over 1000 → 100 bytes (§14.9)."""
    br = parse_range("bytes=0-99", 1000)
    assert br is not None
    assert br.start == 0
    assert br.end == 99
    assert br.length == 100


def test_open_ended_runs_to_eof() -> None:
    """``bytes=100-`` over 1000 → ends at last byte 999 (§14.9)."""
    br = parse_range("bytes=100-", 1000)
    assert br is not None
    assert br.start == 100
    assert br.end == 999
    assert br.length == 900


def test_suffix_takes_last_n_bytes() -> None:
    """``bytes=-500`` over 1000 → last 500 bytes, start 500 (§14.9)."""
    br = parse_range("bytes=-500", 1000)
    assert br is not None
    assert br.start == 500
    assert br.end == 999
    assert br.length == 500


def test_no_header_means_full_200() -> None:
    """A missing ``Range`` header yields ``None`` → full 200 (§14.9)."""
    assert parse_range(None, 1000) is None


def test_end_is_clamped_to_last_byte() -> None:
    """``bytes=0-99999`` over 1000 clamps end to 999 (§14.9)."""
    br = parse_range("bytes=0-99999", 1000)
    assert br is not None
    assert br.end == 999
    assert br.start == 0
    assert br.length == 1000


def test_content_range_header_render() -> None:
    """``Content-Range`` renders as ``bytes 0-99/1000`` (§14.9)."""
    assert content_range_header(ByteRange(0, 99, 1000)) == "bytes 0-99/1000"


def test_out_of_bounds_is_not_satisfiable() -> None:
    """``bytes=2000-3000`` over 1000 is unsatisfiable → False (§14.9)."""
    assert is_satisfiable("bytes=2000-3000", 1000) is False


def test_as_dict_reports_length() -> None:
    """:meth:`ByteRange.as_dict` surfaces the computed ``length`` (§14.9)."""
    assert ByteRange(0, 99, 1000).as_dict()["length"] == 100


def test_as_dict_shape() -> None:
    """:meth:`as_dict` carries all four fields (§14.9)."""
    assert ByteRange(500, 999, 1000).as_dict() == {
        "start": 500,
        "end": 999,
        "total": 1000,
        "length": 500,
    }


def test_in_bounds_range_is_satisfiable() -> None:
    """A normal in-range request is satisfiable → True (§14.9)."""
    assert is_satisfiable("bytes=0-99", 1000) is True


def test_start_past_eof_unsatisfiable() -> None:
    """Start exactly at ``total`` is past EOF → ``None`` (§14.9)."""
    assert parse_range("bytes=1000-1100", 1000) is None


def test_malformed_and_multirange_return_none() -> None:
    """Non-``bytes=`` units, multi-range and junk are unparseable (§14.9)."""
    assert parse_range("items=0-99", 1000) is None
    assert parse_range("bytes=0-99,200-299", 1000) is None
    assert parse_range("bytes=abc-def", 1000) is None
    assert parse_range("bytes=", 1000) is None


def test_reversed_range_rejected() -> None:
    """An end below the start is rejected (§14.9)."""
    assert parse_range("bytes=500-100", 1000) is None


def test_zero_total_never_satisfiable() -> None:
    """An empty body satisfies no byte range (§14.9)."""
    assert parse_range("bytes=0-0", 0) is None
    assert is_satisfiable("bytes=0-0", 0) is False


def test_suffix_larger_than_body_clamps_to_start_zero() -> None:
    """A suffix longer than the body starts at 0 (§14.9)."""
    br = parse_range("bytes=-5000", 1000)
    assert br is not None
    assert br.start == 0
    assert br.end == 999
    assert br.length == 1000

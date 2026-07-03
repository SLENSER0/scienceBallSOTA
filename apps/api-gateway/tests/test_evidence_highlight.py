"""Tests for §14.9 evidence page-highlight span builder."""

from __future__ import annotations

from api_gateway.evidence_highlight import (
    HighlightSpan,
    build_highlight,
    clamp_span,
    overlaps,
)


def test_build_highlight_slices_text() -> None:
    assert build_highlight(1, "hello world", 0, 5).text == "hello"


def test_build_highlight_clamps_overlong_end() -> None:
    span = build_highlight(1, "hello", 0, 999)
    assert span.char_end == 5
    assert span.text == "hello"


def test_build_highlight_records_page() -> None:
    assert build_highlight(7, "hello", 0, 5).page == 7


def test_build_highlight_mid_slice() -> None:
    span = build_highlight(2, "abcdefgh", 2, 5)
    assert span.text == "cde"
    assert (span.char_start, span.char_end) == (2, 5)


def test_clamp_span_negative_start() -> None:
    assert clamp_span(-3, 2, 10) == (0, 2)


def test_clamp_span_start_past_end_keeps_invariant() -> None:
    start, end = clamp_span(8, 3, 10)
    assert start <= end
    assert (start, end) == (8, 8)


def test_clamp_span_clamps_to_page_len() -> None:
    assert clamp_span(3, 100, 10) == (3, 10)


def test_clamp_span_start_beyond_page_len() -> None:
    start, end = clamp_span(50, 60, 10)
    assert (start, end) == (10, 10)
    assert start <= end


def test_clamp_span_both_negative() -> None:
    assert clamp_span(-5, -1, 10) == (0, 0)


def test_overlaps_intersecting_spans_true() -> None:
    a = build_highlight(1, "abcdef", 0, 3)
    b = build_highlight(1, "abcdef", 2, 5)
    assert overlaps(a, b) is True


def test_overlaps_different_pages_false() -> None:
    a = build_highlight(1, "x", 0, 1)
    b = build_highlight(2, "x", 0, 1)
    assert overlaps(a, b) is False


def test_overlaps_touching_intervals_false() -> None:
    # Half-open intervals: [0,3) and [3,6) touch but do not intersect.
    a = build_highlight(1, "abcdef", 0, 3)
    b = build_highlight(1, "abcdef", 3, 6)
    assert overlaps(a, b) is False


def test_overlaps_disjoint_intervals_false() -> None:
    a = build_highlight(1, "abcdef", 0, 2)
    b = build_highlight(1, "abcdef", 4, 6)
    assert overlaps(a, b) is False


def test_overlaps_is_symmetric() -> None:
    a = build_highlight(1, "abcdef", 0, 3)
    b = build_highlight(1, "abcdef", 2, 5)
    assert overlaps(a, b) == overlaps(b, a)


def test_as_dict_keys_and_values() -> None:
    span = build_highlight(1, "hello world", 0, 5)
    d = span.as_dict()
    assert set(d) == {"page", "char_start", "char_end", "text"}
    assert d == {"page": 1, "char_start": 0, "char_end": 5, "text": "hello"}


def test_highlight_span_is_frozen() -> None:
    span = HighlightSpan(page=1, char_start=0, char_end=5, text="hello")
    try:
        span.char_start = 2  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("HighlightSpan should be frozen")

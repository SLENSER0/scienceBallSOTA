"""Tests for §12.11 character-span snippet extraction (`snippet_window`)."""

from __future__ import annotations

from kg_retrievers.snippet_window import Snippet, extract_window

_OPEN = "«"
_CLOSE = "»"


def _make_text(n: int) -> str:
    """Deterministic text of length ``n`` (digits cycling 0-9)."""
    return "".join(str(i % 10) for i in range(n))


def test_bounds_clamped_symmetrically() -> None:
    text = _make_text(200)
    snip = extract_window(text, 100, 110, radius=20)
    assert snip.start == 80
    assert snip.end == 130
    assert snip.text == text[80:130]


def test_span_at_zero_clamps_start_non_negative() -> None:
    text = _make_text(200)
    snip = extract_window(text, 0, 10, radius=20)
    assert snip.start == 0
    assert snip.end == 30
    # No negative index leaked into the window.
    assert snip.text == text[0:30]


def test_radius_larger_than_document_returns_whole_text() -> None:
    text = _make_text(50)
    snip = extract_window(text, 20, 30, radius=1000)
    assert snip.start == 0
    assert snip.end == len(text)
    assert snip.text == text


def test_marker_precedes_target_span() -> None:
    text = _make_text(200)
    snip = extract_window(text, 100, 110, radius=20)
    target = text[100:110]
    # Opening marker sits immediately before the target span.
    assert (_OPEN + target) in snip.highlighted


def test_stripping_markers_reproduces_window() -> None:
    text = _make_text(200)
    snip = extract_window(text, 100, 110, radius=20)
    stripped = snip.highlighted.replace(_OPEN, "").replace(_CLOSE, "")
    assert stripped == snip.text


def test_empty_span_yields_valid_window() -> None:
    text = _make_text(200)
    char_start = char_end = 100
    snip = extract_window(text, char_start, char_end, radius=20)
    assert snip.start <= char_start <= snip.end
    assert snip.text == text[80:120]
    # Empty span -> markers are adjacent, stripping still reproduces window.
    assert snip.highlighted.replace(_OPEN, "").replace(_CLOSE, "") == snip.text


def test_custom_marker_pair() -> None:
    text = _make_text(200)
    snip = extract_window(text, 50, 60, radius=10, marker=("[[", "]]"))
    assert ("[[" + text[50:60] + "]]") in snip.highlighted
    assert snip.highlighted.replace("[[", "").replace("]]", "") == snip.text


def test_as_dict_keys_and_values() -> None:
    text = _make_text(200)
    snip = extract_window(text, 100, 110, radius=20)
    d = snip.as_dict()
    assert set(d) == {"text", "start", "end", "highlighted"}
    assert d["text"] == snip.text
    assert d["start"] == snip.start
    assert d["end"] == snip.end
    assert d["highlighted"] == snip.highlighted


def test_snippet_is_frozen() -> None:
    snip = Snippet(text="ab", start=0, end=2, highlighted="«ab»")
    try:
        snip.start = 5  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("Snippet must be frozen")

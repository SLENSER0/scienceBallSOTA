"""PDF page-map tests — §5.16.

Hand-checked expectations over a small 3-page flat text. Pages are contiguous
half-open spans: page 1 ``[0, 10)``, page 2 ``[10, 25)``, page 4 ``[25, 30)``
(page 3 deliberately absent to prove a gap yields ``None``). We check that an
interior offset maps to its page, that the inclusive-start / exclusive-end
boundaries land on the right side, that offsets outside every span return
``None``, that ``span_for`` round-trips (unknown page → ``None``), that
malformed / duplicate / overlapping spans are rejected, and that ``as_dict`` and
an empty map have the exact canonical shape.
"""

from __future__ import annotations

import pytest

from kg_extractors.page_map import PageMap


def _pm() -> PageMap:
    """Three contiguous pages (1, 2, 4) covering flat offsets 0..29."""
    pm = PageMap()
    pm.add_span(1, 0, 10)
    pm.add_span(2, 10, 25)
    pm.add_span(4, 25, 30)
    return pm


def test_offset_to_page_lookup() -> None:
    pm = _pm()
    # Interior offsets land on their owning page.
    assert pm.page_for(0) == 1
    assert pm.page_for(5) == 1
    assert pm.page_for(17) == 2
    assert pm.page_for(29) == 4


def test_boundaries_half_open() -> None:
    pm = _pm()
    # start is inclusive, end is exclusive — the shared boundary belongs to the
    # next page, never the previous one.
    assert pm.page_for(9) == 1  # last offset of page 1
    assert pm.page_for(10) == 2  # boundary → page 2, not page 1
    assert pm.page_for(24) == 2  # last offset of page 2
    assert pm.page_for(25) == 4  # boundary → page 4


def test_unknown_offset_is_none() -> None:
    pm = _pm()
    assert pm.page_for(-1) is None  # before the first span
    assert pm.page_for(30) is None  # exclusive end of the last span
    assert pm.page_for(999) is None  # far past every span


def test_multiple_pages_full_scan() -> None:
    pm = _pm()
    # Every offset 0..29 resolves; the run-length matches each page's span.
    resolved = [pm.page_for(off) for off in range(30)]
    assert resolved == [1] * 10 + [2] * 15 + [4] * 5
    assert resolved.count(1) == 10
    assert resolved.count(2) == 15
    assert resolved.count(4) == 5


def test_span_for() -> None:
    pm = _pm()
    assert pm.span_for(1) == (0, 10)
    assert pm.span_for(2) == (10, 25)
    assert pm.span_for(4) == (25, 30)
    # An unregistered page yields None (page 3 was never added).
    assert pm.span_for(3) is None
    assert pm.span_for(99) is None


def test_as_dict_shape() -> None:
    pm = _pm()
    d = pm.as_dict()
    assert set(d.keys()) == {"pages", "n"}
    assert d == {
        "pages": {1: [0, 10], 2: [10, 25], 4: [25, 30]},
        "n": 3,
    }
    # Insertion order is preserved in the pages mapping.
    pages = d["pages"]
    assert isinstance(pages, dict)
    assert list(pages.keys()) == [1, 2, 4]
    # as_dict copies its containers — mutating the view never touches the map.
    pages[1] = [999, 999]
    assert pm.span_for(1) == (0, 10)


def test_empty_map() -> None:
    pm = PageMap()
    assert pm.page_for(0) is None
    assert pm.span_for(1) is None
    assert pm.as_dict() == {"pages": {}, "n": 0}


def test_single_char_page() -> None:
    # A one-character page [7, 8): only offset 7 belongs to it.
    pm = PageMap()
    pm.add_span(1, 7, 8)
    assert pm.page_for(6) is None
    assert pm.page_for(7) == 1
    assert pm.page_for(8) is None


def test_empty_span_matches_nothing() -> None:
    # A zero-width span [5, 5) is legal but owns no offset (half-open).
    pm = PageMap()
    pm.add_span(1, 5, 5)
    assert pm.span_for(1) == (5, 5)
    assert pm.page_for(5) is None
    assert pm.page_for(4) is None


def test_add_span_rejects_bad_offsets() -> None:
    pm = PageMap()
    with pytest.raises(ValueError, match="char_start must be >= 0"):
        pm.add_span(1, -1, 5)
    with pytest.raises(ValueError, match="precedes char_start"):
        pm.add_span(2, 10, 4)


def test_add_span_rejects_duplicate_page() -> None:
    pm = PageMap()
    pm.add_span(1, 0, 10)
    with pytest.raises(ValueError, match="already has a span"):
        pm.add_span(1, 10, 20)


def test_add_span_rejects_overlap() -> None:
    pm = PageMap()
    pm.add_span(1, 0, 10)
    # [5, 15) overlaps [0, 10) on 5..9.
    with pytest.raises(ValueError, match="overlaps"):
        pm.add_span(2, 5, 15)

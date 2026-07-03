"""Tests for the running header/footer (page furniture) detector (§5.7/§5.11)."""

from __future__ import annotations

from kg_extractors.page_furniture import (
    Furniture,
    detect_furniture,
    strip_furniture,
)


def _pages() -> list[tuple[int, str]]:
    """Three pages sharing a running header + page numbers, plus body lines."""
    return [
        (1, "ГОСТ 4543-2016\nВведение\n1"),
        (2, "ГОСТ 4543-2016\nТвёрдость стали 40Х\n2"),
        (3, "ГОСТ 4543-2016\nПредел прочности\n3"),
    ]


def test_line_on_every_page_is_returned() -> None:
    """A line present on all pages (>= min_fraction) is flagged as furniture."""
    found = detect_furniture(_pages(), min_fraction=0.6)
    lines = {f.line for f in found}
    assert "ГОСТ 4543-2016" in lines


def test_running_header_kind_is_header_footer() -> None:
    """The repeated running title classifies as header_footer, not page_number."""
    found = detect_furniture(_pages(), min_fraction=0.6)
    header = next(f for f in found if f.line == "ГОСТ 4543-2016")
    assert header.kind == "header_footer"
    assert header.pages == (1, 2, 3)


def test_bare_page_number_kind() -> None:
    """A line that is only a bare page number is classified as page_number."""
    pages = [
        (1, "Header line\n1"),
        (2, "Header line\n2"),
        (3, "Header line\n3"),
    ]
    found = detect_furniture(pages, min_fraction=0.6)
    # Each single digit appears on only 1/3 pages, so the digits themselves are
    # not flagged; use a repeated page-number style marker instead.
    pages2 = [
        (1, "Header line\nСтр. 5"),
        (2, "Header line\nСтр. 5"),
        (3, "Header line\nСтр. 5"),
    ]
    found2 = detect_furniture(pages2, min_fraction=0.6)
    pn = next(f for f in found2 if f.line == "Стр. 5")
    assert pn.kind == "page_number"
    # And the header on the first fixture is header_footer.
    assert any(f.kind == "header_footer" for f in found)


def test_unique_body_line_not_returned() -> None:
    """A line appearing on a single page is not flagged as furniture."""
    found = detect_furniture(_pages(), min_fraction=0.6)
    lines = {f.line for f in found}
    assert "Твёрдость стали 40Х" not in lines
    assert "Предел прочности" not in lines


def test_strip_removes_flagged_keeps_others() -> None:
    """strip_furniture drops exactly the flagged lines and keeps body lines."""
    found = detect_furniture(_pages(), min_fraction=0.6)
    cleaned = strip_furniture(_pages(), found)
    joined = "\n".join(text for _, text in cleaned)
    assert "ГОСТ 4543-2016" not in joined
    assert "Твёрдость стали 40Х" in joined
    assert "Предел прочности" in joined
    assert "Введение" in joined


def test_line_on_one_of_three_pages_not_flagged() -> None:
    """A line on 1/3 pages with min_fraction=0.6 is below threshold."""
    pages = [
        (1, "Only here\nShared"),
        (2, "Shared"),
        (3, "Shared"),
    ]
    found = detect_furniture(pages, min_fraction=0.6)
    lines = {f.line for f in found}
    assert "Only here" not in lines
    assert "Shared" in lines


def test_empty_input_yields_empty_list() -> None:
    """Empty pages input yields an empty result list."""
    assert detect_furniture([], min_fraction=0.6) == []


def test_as_dict_pages_is_list() -> None:
    """Furniture.as_dict()['pages'] is a list (not a tuple)."""
    fur = Furniture(line="Header", pages=(1, 2, 3), kind="header_footer")
    d = fur.as_dict()
    assert isinstance(d["pages"], list)
    assert d["pages"] == [1, 2, 3]
    assert d["line"] == "Header"
    assert d["kind"] == "header_footer"


def test_furniture_is_frozen() -> None:
    """Furniture is an immutable frozen dataclass."""
    import dataclasses

    fur = Furniture(line="x", pages=(1,), kind="page_number")
    try:
        fur.line = "y"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - guards against a non-frozen regression
        raise AssertionError("Furniture must be frozen")

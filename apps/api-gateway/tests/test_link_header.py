"""Tests for the RFC 5988 ``Link`` header builder (§14.2).

Проверяем вычисление ``first``/``prev``/``next``/``last`` и рендеринг заголовка
на маленьких, руками просчитанных выборках.
"""

from __future__ import annotations

import pytest
from api_gateway.link_header import LinkSet, build_links, render


def test_first_always_offset_zero() -> None:
    """``first`` всегда указывает на ``offset=0`` / first pins offset 0 (§14.2)."""
    assert build_links("/e", 0, 10, 25).first == "/e?offset=0&limit=10"
    assert build_links("/e", 20, 10, 25).first == "/e?offset=0&limit=10"


def test_prev_none_on_first_page() -> None:
    """``prev`` пуст на первой странице / prev is None at offset 0 (§14.2)."""
    assert build_links("/e", 0, 10, 25).prev is None


def test_prev_steps_back_by_limit() -> None:
    """``prev`` отступает на ``limit`` назад / prev goes back one page (§14.2)."""
    assert build_links("/e", 10, 10, 25).prev == "/e?offset=0&limit=10"
    assert build_links("/e", 20, 10, 25).prev == "/e?offset=10&limit=10"


def test_prev_clamped_to_zero() -> None:
    """``prev`` не уходит ниже нуля / prev clamps at 0 (§14.2)."""
    assert build_links("/e", 5, 10, 25).prev == "/e?offset=0&limit=10"


def test_next_present_when_more_pages() -> None:
    """``next`` есть, пока есть следующая страница / next when more (§14.2)."""
    assert build_links("/e", 0, 10, 25).next == "/e?offset=10&limit=10"
    assert build_links("/e", 10, 10, 25).next == "/e?offset=20&limit=10"


def test_next_none_on_last_page() -> None:
    """``next`` пуст на последней странице / next is None at end (§14.2)."""
    assert build_links("/e", 20, 10, 25).next is None


def test_last_is_largest_multiple_below_total() -> None:
    """Смещение ``last`` — наибольшее кратное ниже ``total`` (§14.2)."""
    assert build_links("/e", 0, 10, 25).last == "/e?offset=20&limit=10"
    # Exact multiple: total=20 → last page begins at offset 10.
    assert build_links("/e", 0, 10, 20).last == "/e?offset=10&limit=10"


def test_single_short_page_has_no_neighbours() -> None:
    """Одна короткая страница без соседей / lone page has no prev/next (§14.2)."""
    links = build_links("/e", 0, 10, 5)
    assert links.next is None
    assert links.prev is None
    assert links.last == "/e?offset=0&limit=10"


def test_empty_total_last_offset_zero() -> None:
    """Пустая выборка: ``last`` = offset 0 / empty total → offset 0 (§14.2)."""
    links = build_links("/e", 0, 10, 0)
    assert links.last == "/e?offset=0&limit=10"
    assert links.next is None
    assert links.prev is None


def test_render_emits_rfc5988_entries() -> None:
    """Рендер выдаёт записи RFC 5988 / render emits <url>; rel=... (§14.2)."""
    header = render(build_links("/e", 0, 10, 25))
    assert 'rel="next"' in header
    assert "</e?offset=10&limit=10>" in header
    assert 'rel="first"' in header
    assert 'rel="last"' in header


def test_render_order_and_omits_none() -> None:
    """Порядок first→prev→next→last, ``None`` пропущены / order & skip (§14.2)."""
    header = render(build_links("/e", 0, 10, 25))
    # prev is None here → must not appear; order first < next < last.
    assert 'rel="prev"' not in header
    assert header.index('rel="first"') < header.index('rel="next"')
    assert header.index('rel="next"') < header.index('rel="last"')
    assert ", " in header


def test_render_all_none_is_empty() -> None:
    """Полностью пустой набор → пустая строка / all-None renders empty (§14.2)."""
    assert render(LinkSet(first=None, prev=None, next=None, last=None)) == ""


def test_as_dict_round_trip() -> None:
    """``as_dict`` содержит все четыре отношения / dict has 4 rels (§14.2)."""
    d = build_links("/e", 0, 10, 25).as_dict()
    assert d["last"] == "/e?offset=20&limit=10"
    assert d["prev"] is None
    assert set(d) == {"first", "prev", "next", "last"}


def test_zero_limit_rejected() -> None:
    """Нулевой ``limit`` отвергается / non-positive limit raises (§14.2)."""
    with pytest.raises(ValueError):
        build_links("/e", 0, 0, 25)

"""§10.7 tests — source-catalog search + pagination helpers.

RU: Проверяем свободный поиск (регистр/подстрока по name и source_id),
AND-комбинацию lab+q, границы постраничной выдачи и ascending-сортировку.
EN: Cover free-text search (ci substring over name and source_id), the lab+q
AND combination, pagination boundaries, and ascending sort.
"""

from __future__ import annotations

import pytest

from kg_common.metadata.catalog_source_query import (
    CatalogPage,
    paginate,
    query,
    search_cards,
)


def _cards() -> list[dict[str, object]]:
    """RU: Небольшой набор карточек. EN: A small hand-checkable card set."""
    return [
        {"source_id": "src-alpha-01", "name": "Alpha Steel", "lab": "L1", "owner": "u1"},
        {"source_id": "beta-02", "name": "Beta Iron", "lab": "L2", "owner": "u2"},
        {"source_id": "gamma-alpha-03", "name": "Gamma Copper", "lab": "L1", "owner": "u1"},
    ]


def test_search_q_matches_name_case_insensitively() -> None:
    """RU: q='alpha' находит 'Alpha Steel'. EN: q matches name ignoring case."""
    hits = search_cards(_cards(), q="alpha")
    names = {card["name"] for card in hits}
    assert "Alpha Steel" in names


def test_search_q_matches_source_id_substring() -> None:
    """RU: q по подстроке source_id. EN: q matches a source_id substring."""
    hits = search_cards(_cards(), q="gamma-alpha")
    assert [card["name"] for card in hits] == ["Gamma Copper"]


def test_search_lab_and_q_require_both() -> None:
    """RU: lab+q — оба условия. EN: combined lab+q require BOTH to match."""
    # 'alpha' matches src-alpha-01 (L1) and gamma-alpha-03 (L1); lab=L2 excludes both.
    assert search_cards(_cards(), q="alpha", lab="L2") == []
    hits = search_cards(_cards(), q="alpha", lab="L1")
    assert {card["source_id"] for card in hits} == {"src-alpha-01", "gamma-alpha-03"}


def test_search_q_none_or_empty_returns_all() -> None:
    """RU: q=None/'' — все карточки. EN: q=None (or '') returns all cards."""
    cards = _cards()
    assert search_cards(cards, q=None) == cards
    assert search_cards(cards, q="") == cards


def test_search_preserves_input_order() -> None:
    """RU: Порядок входа сохранён. EN: Input order is preserved."""
    hits = search_cards(_cards(), lab="L1")
    assert [card["source_id"] for card in hits] == ["src-alpha-01", "gamma-alpha-03"]


def test_paginate_first_page_has_more() -> None:
    """RU: 5 строк, 0,2 → has_more. EN: paginate(5 rows,0,2) → total 5, has_more."""
    page = paginate(list(range(5)), 0, 2)
    assert isinstance(page, CatalogPage)
    assert page.total == 5
    assert len(page.items) == 2
    assert page.has_more is True


def test_paginate_last_page_no_more() -> None:
    """RU: 5 строк, 4,2 → 1 элемент. EN: paginate(5 rows,4,2) → 1 item, no more."""
    page = paginate(list(range(5)), 4, 2)
    assert len(page.items) == 1
    assert page.has_more is False


def test_paginate_rejects_non_positive_limit() -> None:
    """RU: limit<=0 → ValueError. EN: paginate(rows, limit=0) raises ValueError."""
    with pytest.raises(ValueError):
        paginate(list(range(5)), limit=0)


def test_paginate_rejects_negative_offset() -> None:
    """RU: offset<0 → ValueError. EN: negative offset raises ValueError."""
    with pytest.raises(ValueError):
        paginate(list(range(5)), offset=-1)


def test_paginate_as_dict_roundtrip() -> None:
    """RU: as_dict отдаёт плоский словарь. EN: as_dict returns a flat mapping."""
    page = paginate([{"source_id": "a"}], 0, 20)
    payload = page.as_dict()
    assert payload["total"] == 1
    assert payload["items"] == [{"source_id": "a"}]
    assert payload["has_more"] is False


def test_query_sorts_ascending_by_name() -> None:
    """RU: sort_by='name' — по возрастанию. EN: query sorts items ascending."""
    page = query(_cards(), sort_by="name")
    assert [card["name"] for card in page.items] == [
        "Alpha Steel",
        "Beta Iron",
        "Gamma Copper",
    ]


def test_query_combines_search_and_pagination() -> None:
    """RU: query: поиск + страница. EN: query runs search then paginate."""
    page = query(_cards(), lab="L1", sort_by="name", offset=0, limit=1)
    assert page.total == 2
    assert len(page.items) == 1
    assert page.items[0]["name"] == "Alpha Steel"
    assert page.has_more is True

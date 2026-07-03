"""Tests for CSL-JSON export — проверка экспорта CSL-JSON (§22.6).

Hand-checkable coverage of the eight spec assertions plus round-trip and
omission behaviour of :mod:`kg_common.csl_json_export`.
"""

from __future__ import annotations

import json

from kg_common.csl_json_export import (
    CslItem,
    paper_to_csl,
    papers_to_csl_json,
    split_name,
)


def _item(**over: object) -> CslItem:
    """A fully-populated :class:`CslItem` with per-test field overrides."""
    base: dict[str, object] = {
        "id": "smith2020",
        "type": "article-journal",
        "title": "On Widgets",
        "author": ({"family": "Smith", "given": "John"},),
        "issued_year": 2020,
        "doi": "10.1/abc",
        "container_title": "Journal of Widgets",
    }
    base.update(over)
    return CslItem(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# split_name                                                                   #
# --------------------------------------------------------------------------- #


def test_split_name_comma_form() -> None:
    """(1) ``"Last, First"`` splits into family/given — форма с запятой."""
    assert split_name("Smith, John") == {"family": "Smith", "given": "John"}


def test_split_name_space_form() -> None:
    """(2) ``"First Last"`` -> last token is family — форма с пробелом."""
    assert split_name("John Smith") == {"family": "Smith", "given": "John"}


def test_split_name_multi_given() -> None:
    """A middle name stays part of ``given`` — составное имя."""
    assert split_name("John Q Public") == {"family": "Public", "given": "John Q"}


def test_split_name_single_token() -> None:
    """A single token yields ``family`` only — один токен."""
    assert split_name("Plato") == {"family": "Plato"}


def test_split_name_comma_no_given() -> None:
    """Comma form with empty given yields ``family`` only — пустое имя."""
    assert split_name("Smith,") == {"family": "Smith"}


# --------------------------------------------------------------------------- #
# CslItem.as_dict                                                              #
# --------------------------------------------------------------------------- #


def test_as_dict_type_is_article_journal() -> None:
    """(3) ``type`` is the CSL ``article-journal`` — тип ссылки."""
    assert _item().as_dict()["type"] == "article-journal"


def test_as_dict_issued_date_parts() -> None:
    """(4) year 2020 -> ``issued`` date-parts — обёртка года."""
    assert _item(issued_year=2020).as_dict()["issued"] == {"date-parts": [[2020]]}


def test_as_dict_missing_doi_omitted() -> None:
    """(5) ``doi=None`` -> no ``DOI`` key — пропуск отсутствующего DOI."""
    assert "DOI" not in _item(doi=None).as_dict()


def test_as_dict_container_title() -> None:
    """(6) venue maps to ``container-title`` — журнал/площадка."""
    assert _item(container_title="J. Widgets").as_dict()["container-title"] == "J. Widgets"


def test_as_dict_author_shape() -> None:
    """Authors render as a list of ``{family, given}`` dicts — форма авторов."""
    got = _item().as_dict()["author"]
    assert got == [{"family": "Smith", "given": "John"}]


def test_as_dict_no_year_omits_issued() -> None:
    """No year -> no ``issued`` key — отсутствие даты."""
    assert "issued" not in _item(issued_year=None).as_dict()


def test_as_dict_no_authors_omits_author() -> None:
    """Empty author tuple -> no ``author`` key — нет авторов."""
    assert "author" not in _item(author=()).as_dict()


def test_as_dict_always_has_core_fields() -> None:
    """``id``/``type``/``title`` are always present — обязательные поля."""
    got = _item().as_dict()
    assert got["id"] == "smith2020"
    assert got["title"] == "On Widgets"


# --------------------------------------------------------------------------- #
# paper_to_csl                                                                 #
# --------------------------------------------------------------------------- #


def test_paper_to_csl_full() -> None:
    """A rich metadata dict maps every field — полный словарь."""
    meta = {
        "id": "smith2020",
        "title": "On Widgets",
        "authors": ["Smith, John", "Doe, Jane"],
        "year": 2020,
        "doi": "10.1/abc",
        "venue": "Journal of Widgets",
    }
    item = paper_to_csl(meta)
    got = item.as_dict()
    assert got["type"] == "article-journal"
    assert got["issued"] == {"date-parts": [[2020]]}
    assert got["DOI"] == "10.1/abc"
    assert got["container-title"] == "Journal of Widgets"
    assert got["author"] == [
        {"family": "Smith", "given": "John"},
        {"family": "Doe", "given": "Jane"},
    ]


def test_paper_to_csl_venue_from_journal() -> None:
    """(6) ``journal`` fills ``container-title`` when ``venue`` absent — фолбэк."""
    item = paper_to_csl({"id": "x", "journal": "Nature"})
    assert item.as_dict()["container-title"] == "Nature"


def test_paper_to_csl_id_from_doc_id() -> None:
    """``doc_id`` is used as the ``id`` fallback — источник id."""
    item = paper_to_csl({"doc_id": "p42", "title": "T"})
    assert item.as_dict()["id"] == "p42"


def test_paper_to_csl_string_author() -> None:
    """A bare string author becomes a single name entry — один автор строкой."""
    item = paper_to_csl({"id": "x", "author": "John Smith"})
    assert item.as_dict()["author"] == [{"family": "Smith", "given": "John"}]


def test_paper_to_csl_year_coerced() -> None:
    """A stringy ``year`` is coerced to int in date-parts — приведение года."""
    item = paper_to_csl({"id": "x", "year": "1999"})
    assert item.as_dict()["issued"] == {"date-parts": [[1999]]}


def test_paper_to_csl_sparse_omits() -> None:
    """A sparse dict omits every optional field — разреженный словарь."""
    got = paper_to_csl({"id": "x"}).as_dict()
    assert set(got) == {"id", "type", "title"}


# --------------------------------------------------------------------------- #
# papers_to_csl_json                                                           #
# --------------------------------------------------------------------------- #


def test_papers_to_csl_json_length_and_loadable() -> None:
    """(7) Output is a JSON list of the same length as input — round-trip."""
    metas = [
        {"id": "a", "title": "A", "year": 2001},
        {"id": "b", "title": "B", "authors": ["Doe, Jane"]},
        {"id": "c", "title": "C", "doi": "10.1/c"},
    ]
    text = papers_to_csl_json(metas)
    parsed = json.loads(text)
    assert isinstance(parsed, list)
    assert len(parsed) == len(metas)
    assert parsed[0]["id"] == "a"


def test_papers_to_csl_json_empty() -> None:
    """(8) Empty input yields the empty array literal — пустой ввод."""
    assert papers_to_csl_json([]) == "[]"


def test_papers_to_csl_json_deterministic() -> None:
    """``sort_keys`` makes the serialisation byte-stable — детерминизм."""
    metas = [{"id": "a", "title": "A", "doi": "10.1/a", "venue": "V", "year": 2000}]
    assert papers_to_csl_json(metas) == papers_to_csl_json(metas)


def test_papers_to_csl_json_keys_sorted() -> None:
    """Keys within an item are sorted (DOI before id before type) — порядок ключей."""
    text = papers_to_csl_json([{"id": "a", "title": "A", "doi": "10.1/a"}])
    # sort_keys orders uppercase 'DOI' before lowercase keys.
    assert text.index('"DOI"') < text.index('"id"') < text.index('"type"')

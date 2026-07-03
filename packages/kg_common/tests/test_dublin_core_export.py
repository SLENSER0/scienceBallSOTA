"""Tests for the simple Dublin Core (OAI-DC) exporter — проверки экспорта (§22)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from kg_common.dublin_core_export import (
    DC15_TERMS,
    DublinCoreRecord,
    from_paper,
    to_xml,
)

_NS = {"dc": "http://purl.org/dc/elements/1.1/"}


def test_unknown_term_raises() -> None:
    """Only DC15 terms are accepted; an unknown term raises ``ValueError``."""
    DublinCoreRecord(elements=(("title", "Ok"),))  # valid, no raise
    with pytest.raises(ValueError, match="unknown Dublin Core term"):
        DublinCoreRecord(elements=(("author", "Nope"),))


def test_all_dc15_terms_accepted() -> None:
    """Every one of the fifteen DC15 terms constructs without error."""
    pairs = tuple((term, "v") for term in sorted(DC15_TERMS))
    record = DublinCoreRecord(elements=pairs)
    assert len(record.elements) == 15


def test_two_authors_two_creator_elements() -> None:
    """Two authors -> two ``dc:creator`` pairs and two XML elements."""
    meta = {"title": "T", "authors": ["Ada Lovelace", "Alan Turing"]}
    record = from_paper(meta)
    creators = [v for term, v in record.elements if term == "creator"]
    assert creators == ["Ada Lovelace", "Alan Turing"]
    root = ET.fromstring(to_xml(record))
    assert len(root.findall("dc:creator", _NS)) == 2


def test_missing_doi_no_identifier() -> None:
    """A metadata dict without ``doi`` yields no ``dc:identifier`` element."""
    record = from_paper({"title": "T", "year": 2020})
    assert all(term != "identifier" for term, _ in record.elements)
    root = ET.fromstring(to_xml(record))
    assert root.findall("dc:identifier", _NS) == []


def test_full_field_mapping() -> None:
    """title/authors/year/doi/venue map to the right DC terms and values."""
    meta = {
        "title": "Deep Nets",
        "authors": ["Smith, John"],
        "year": 2021,
        "doi": "10.1/abc",
        "venue": "NeurIPS",
    }
    record = from_paper(meta)
    assert record.elements == (
        ("title", "Deep Nets"),
        ("creator", "Smith, John"),
        ("date", "2021"),
        ("identifier", "10.1/abc"),
        ("source", "NeurIPS"),
    )


def test_to_xml_parses_via_elementtree() -> None:
    """``to_xml`` output is well-formed and parses via ElementTree."""
    record = from_paper({"title": "T", "authors": ["A"], "year": 1999})
    root = ET.fromstring(to_xml(record))
    assert root.tag.endswith("}dc")  # oai_dc:dc in its namespace
    assert root.find("dc:title", _NS).text == "T"
    assert root.find("dc:date", _NS).text == "1999"


def test_less_than_is_escaped() -> None:
    """A value containing ``<`` is escaped to ``&lt;`` in the raw XML."""
    record = DublinCoreRecord(elements=(("title", "a < b & c"),))
    xml = to_xml(record)
    assert "&lt;" in xml
    assert "&amp;" in xml
    assert "<dc:title>a < b" not in xml  # the literal '<' is not emitted
    # Escaped text still parses and decodes back to the original value.
    root = ET.fromstring(xml)
    assert root.find("dc:title", _NS).text == "a < b & c"


def test_element_order_matches_tuple_order() -> None:
    """Output element order matches the ``elements`` tuple order."""
    record = DublinCoreRecord(
        elements=(
            ("subject", "s1"),
            ("title", "t1"),
            ("creator", "c1"),
        )
    )
    root = ET.fromstring(to_xml(record))
    tags = [child.tag.split("}")[-1] for child in root]
    assert tags == ["subject", "title", "creator"]


def test_from_paper_empty_yields_empty_record() -> None:
    """``from_paper({})`` yields an empty-element record; XML is just the root."""
    record = from_paper({})
    assert record.elements == ()
    root = ET.fromstring(to_xml(record))
    assert list(root) == []


def test_as_dict_round_trips() -> None:
    """``as_dict()['elements']`` re-tuples back to an equal record."""
    original = from_paper({"title": "T", "authors": ["A", "B"], "year": 2000, "doi": "10.x/y"})
    data = original.as_dict()
    rebuilt = DublinCoreRecord(elements=tuple(tuple(pair) for pair in data["elements"]))
    assert rebuilt == original


def test_author_singular_string_key() -> None:
    """A singular ``author`` string maps to exactly one ``dc:creator``."""
    record = from_paper({"author": "Solo Writer"})
    assert record.elements == (("creator", "Solo Writer"),)


def test_venue_falls_back_to_journal() -> None:
    """When ``venue`` is absent, ``journal`` supplies ``dc:source``."""
    record = from_paper({"journal": "JMLR"})
    assert record.elements == (("source", "JMLR"),)

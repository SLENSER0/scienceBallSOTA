"""Tests for DataCite 4.4 metadata export — проверка экспорта DataCite (§22).

Hand-checkable coverage of the spec assertions: the output parses via
:func:`ElementTree.fromstring`, the root local-name is ``resource``, the
``<identifier>`` carries the DOI with ``identifierType="DOI"``, two creators
produce two ``<creator>`` children, ``<publicationYear>`` is the year as a
string, an ``&`` in a title is escaped to ``&amp;``, ``resourceTypeGeneral`` is
``Dataset`` and :meth:`DataCiteRecord.as_dict` returns a ``tuple[str, ...]`` of
creators.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from kg_common.datacite_metadata_export import (
    DataCiteRecord,
    build_record,
    to_xml,
)

_NS = "http://datacite.org/schema/kernel-4"


def _local(tag: str) -> str:
    """Strip the ``{namespace}`` prefix from an ElementTree tag — локальное имя."""
    return tag.rpartition("}")[2]


def _find(root: ET.Element, name: str) -> ET.Element:
    """Find the first descendant whose local-name is ``name`` — поиск по имени."""
    for el in root.iter():
        if _local(el.tag) == name:
            return el
    raise AssertionError(f"no <{name}> element found")


def _record(**over: object) -> DataCiteRecord:
    """A fully-populated :class:`DataCiteRecord` with per-test overrides."""
    base: dict[str, object] = {
        "identifier": "10.1234/kg-snapshot-2026",
        "creators": ("Ada Lovelace", "Alan Turing"),
        "title": "Science-Ball KG Snapshot",
        "publisher": "Science-Ball",
        "publication_year": 2026,
        "resource_type": "Dataset",
    }
    base.update(over)
    return DataCiteRecord(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# build_record                                                                 #
# --------------------------------------------------------------------------- #


def test_build_record_defaults_resource_type() -> None:
    """``resource_type`` defaults to ``Dataset`` — значение по умолчанию."""
    r = build_record(
        identifier="10.1/x",
        creators=("A",),
        title="T",
        publisher="P",
        publication_year=2020,
    )
    assert r.resource_type == "Dataset"


def test_build_record_coerces_year_and_creators() -> None:
    """Year is coerced to int and creators to a str tuple — приведение типов."""
    r = build_record(
        identifier="10.1/x",
        creators=("A", "B"),
        title="T",
        publisher="P",
        publication_year="1999",  # type: ignore[arg-type]
    )
    assert r.publication_year == 1999
    assert r.creators == ("A", "B")


def test_build_record_strips_whitespace() -> None:
    """Surrounding whitespace is stripped from fields — обрезка пробелов."""
    r = build_record(
        identifier="  10.1/x  ",
        creators=("  Ada  ",),
        title="  T  ",
        publisher="  P  ",
        publication_year=2020,
    )
    assert r.identifier == "10.1/x"
    assert r.creators == ("Ada",)
    assert r.title == "T"


# --------------------------------------------------------------------------- #
# as_dict                                                                      #
# --------------------------------------------------------------------------- #


def test_as_dict_creators_is_tuple_of_str() -> None:
    """``as_dict()['creators']`` is a tuple of str — кортеж строк."""
    creators = _record().as_dict()["creators"]
    assert isinstance(creators, tuple)
    assert all(isinstance(name, str) for name in creators)


def test_as_dict_year_stays_int() -> None:
    """``publication_year`` stays an int in the mapping — год остаётся int."""
    assert _record(publication_year=2026).as_dict()["publication_year"] == 2026


def test_as_dict_roundtrips_fields() -> None:
    """Every constructor field appears in the mapping — обход полей."""
    got = _record().as_dict()
    assert got["identifier"] == "10.1234/kg-snapshot-2026"
    assert got["title"] == "Science-Ball KG Snapshot"
    assert got["publisher"] == "Science-Ball"
    assert got["resource_type"] == "Dataset"


# --------------------------------------------------------------------------- #
# to_xml                                                                       #
# --------------------------------------------------------------------------- #


def test_to_xml_parses() -> None:
    """Output parses via ``ElementTree.fromstring`` — вывод парсится."""
    root = ET.fromstring(to_xml(_record()))
    assert root is not None


def test_to_xml_root_local_name_is_resource() -> None:
    """Root local-name is ``resource`` — корневой элемент."""
    root = ET.fromstring(to_xml(_record()))
    assert _local(root.tag) == "resource"


def test_to_xml_root_in_datacite_namespace() -> None:
    """Root sits in the DataCite kernel-4 namespace — пространство имён."""
    root = ET.fromstring(to_xml(_record()))
    assert root.tag == f"{{{_NS}}}resource"


def test_to_xml_identifier_text_and_type() -> None:
    """``<identifier>`` text is the DOI with ``identifierType="DOI"``."""
    root = ET.fromstring(to_xml(_record(identifier="10.9/dataset")))
    ident = _find(root, "identifier")
    assert ident.text == "10.9/dataset"
    assert ident.attrib["identifierType"] == "DOI"


def test_to_xml_two_creators_two_children() -> None:
    """Two creators produce two ``<creator>`` children — два автора."""
    root = ET.fromstring(to_xml(_record(creators=("Ada Lovelace", "Alan Turing"))))
    creators = _find(root, "creators")
    kids = [el for el in creators if _local(el.tag) == "creator"]
    assert len(kids) == 2


def test_to_xml_creator_names() -> None:
    """Each ``<creatorName>`` carries its author name — имена авторов."""
    root = ET.fromstring(to_xml(_record(creators=("Ada Lovelace", "Alan Turing"))))
    names = [_local(el.tag) == "creatorName" and el.text for el in root.iter()]
    names = [n for n in names if n]
    assert names == ["Ada Lovelace", "Alan Turing"]


def test_to_xml_single_title() -> None:
    """A single ``<title>`` holds the dataset title — заголовок."""
    root = ET.fromstring(to_xml(_record(title="My Dataset")))
    assert _find(root, "title").text == "My Dataset"


def test_to_xml_publisher() -> None:
    """``<publisher>`` holds the issuing organisation — издатель."""
    root = ET.fromstring(to_xml(_record(publisher="Acme Labs")))
    assert _find(root, "publisher").text == "Acme Labs"


def test_to_xml_publication_year_is_int_as_string() -> None:
    """``<publicationYear>`` text is the int as a string — год строкой."""
    root = ET.fromstring(to_xml(_record(publication_year=2026)))
    assert _find(root, "publicationYear").text == "2026"


def test_to_xml_ampersand_escaped() -> None:
    """A title with ``&`` is escaped to ``&amp;`` in the raw XML — экранирование."""
    xml = to_xml(_record(title="Foo & Bar"))
    assert "&amp;" in xml
    assert "Foo & Bar" not in xml
    # ...and it round-trips back to the literal ampersand on parse.
    root = ET.fromstring(xml)
    assert _find(root, "title").text == "Foo & Bar"


def test_to_xml_angle_brackets_escaped() -> None:
    """``<`` and ``>`` in a title are escaped — экранирование скобок."""
    xml = to_xml(_record(title="a < b > c"))
    assert "&lt;" in xml
    assert "&gt;" in xml
    root = ET.fromstring(xml)
    assert _find(root, "title").text == "a < b > c"


def test_to_xml_resource_type_general_is_dataset() -> None:
    """``resourceTypeGeneral`` attr equals ``Dataset`` — общий тип ресурса."""
    root = ET.fromstring(to_xml(_record()))
    resource_type = _find(root, "resourceType")
    assert resource_type.attrib["resourceTypeGeneral"] == "Dataset"


def test_to_xml_has_declaration() -> None:
    """Output opens with an XML declaration — XML-декларация."""
    assert to_xml(_record()).startswith("<?xml")


def test_to_xml_zero_creators() -> None:
    """No creators -> an empty ``<creators>`` block still parses — нет авторов."""
    root = ET.fromstring(to_xml(_record(creators=())))
    creators = _find(root, "creators")
    kids = [el for el in creators if _local(el.tag) == "creator"]
    assert kids == []

"""Dataset metadata -> DataCite 4.4 XML — экспорт метаданных для DOI (§22).

A pure-stdlib serialiser (:mod:`xml.etree.ElementTree` only) that renders KG
snapshot metadata as **DataCite Metadata Schema 4.4** XML — the schema a DOI
registration agency (DataCite/Fabrica) ingests when minting a DOI for an
exported knowledge-graph snapshot. This complements the citation exporters
already in the repo (BibTeX, RIS, CSL-JSON) by producing the *registration*
side rather than a bibliography entry — сторона регистрации DOI.

The emitted document is a single ``<resource>`` root in the DataCite namespace
carrying the five mandatory properties: ``<identifier>`` (the DOI, with
``identifierType="DOI"``), ``<creators>`` (one ``<creator>``/``<creatorName>``
per author), ``<titles>`` (one ``<title>``), ``<publisher>``,
``<publicationYear>`` and ``<resourceType>`` (with
``resourceTypeGeneral="Dataset"``). Everything is side-effect free: no I/O, no
wall-clock, no globals — детерминированный вывод.

XML-special characters (``&``, ``<``, ``>``) are escaped by
:mod:`ElementTree` on serialisation, so a title containing ``&`` round-trips as
``&amp;`` — экранирование спецсимволов.

Public API:

* :class:`DataCiteRecord` — frozen record with :meth:`as_dict`.
* :func:`build_record` — construct a :class:`DataCiteRecord` from fields.
* :func:`to_xml` — serialise a record to DataCite 4.4 XML text.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

__all__ = [
    "DataCiteRecord",
    "build_record",
    "to_xml",
]

#: DataCite Metadata Schema 4.4 namespace URI — пространство имён DataCite (§22).
_DATACITE_NS: str = "http://datacite.org/schema/kernel-4"

#: Schema location advertised on the root element — расположение схемы.
_SCHEMA_LOCATION: str = (
    "http://datacite.org/schema/kernel-4 http://schema.datacite.org/meta/kernel-4.4/metadata.xsd"
)

#: XML Schema instance namespace — пространство имён XSD-инстанса.
_XSI_NS: str = "http://www.w3.org/2001/XMLSchema-instance"


# --------------------------------------------------------------------------- #
# Record — запись метаданных DataCite                                          #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class DataCiteRecord:
    """One DataCite 4.4 metadata record — одна запись метаданных (§22).

    Holds the five mandatory DataCite properties plus the resource type.
    ``identifier`` is the DOI string (registered with ``identifierType="DOI"``);
    ``creators`` is a tuple of author display names; ``title`` is the dataset
    title; ``publisher`` the issuing organisation; ``publication_year`` the
    integer year; ``resource_type`` a free-text label whose *general* category
    is always ``Dataset``. Frozen value object; :meth:`as_dict` renders the
    canonical mapping.
    """

    identifier: str
    creators: tuple[str, ...]
    title: str
    publisher: str
    publication_year: int
    resource_type: str = "Dataset"

    def as_dict(self) -> dict[str, object]:
        """Return the canonical mapping — каноническое представление записи.

        ``creators`` is always a ``tuple[str, ...]``; ``publication_year`` stays
        an ``int``; every other field is a ``str``. The shape mirrors the
        constructor arguments one-to-one for hand-checkable round-tripping.
        """
        return {
            "identifier": self.identifier,
            "creators": self.creators,
            "title": self.title,
            "publisher": self.publisher,
            "publication_year": self.publication_year,
            "resource_type": self.resource_type,
        }


# --------------------------------------------------------------------------- #
# Build — построение записи                                                    #
# --------------------------------------------------------------------------- #


def build_record(
    identifier: str,
    creators: tuple[str, ...],
    title: str,
    publisher: str,
    publication_year: int,
    resource_type: str = "Dataset",
) -> DataCiteRecord:
    """Build a :class:`DataCiteRecord` from fields — построить запись (§22).

    Creators are coerced to a tuple of stripped strings (any iterable of names
    is accepted); the DOI, title and publisher are stringified and stripped;
    ``publication_year`` is coerced to ``int``. ``resource_type`` defaults to
    ``Dataset`` — значения по умолчанию.
    """
    names = tuple(str(name).strip() for name in creators)
    return DataCiteRecord(
        identifier=str(identifier).strip(),
        creators=names,
        title=str(title).strip(),
        publisher=str(publisher).strip(),
        publication_year=int(publication_year),
        resource_type=str(resource_type).strip() or "Dataset",
    )


# --------------------------------------------------------------------------- #
# Serialise — сериализация в XML                                               #
# --------------------------------------------------------------------------- #


def to_xml(r: DataCiteRecord) -> str:
    """Serialise a record to DataCite 4.4 XML text — сериализация в XML (§22).

    Builds a ``<resource>`` root in the DataCite namespace with the mandatory
    ``<identifier identifierType="DOI">``, a ``<creators>`` block holding one
    ``<creator><creatorName>`` per author, a ``<titles>`` block with a single
    ``<title>``, ``<publisher>``, ``<publicationYear>`` and a
    ``<resourceType resourceTypeGeneral="Dataset">``. :mod:`ElementTree`
    escapes ``&``/``<``/``>`` in text content, so a title with ``&`` renders as
    ``&amp;``. Returns a Unicode string with an XML declaration.
    """
    resource = ET.Element(
        f"{{{_DATACITE_NS}}}resource",
        {
            f"{{{_XSI_NS}}}schemaLocation": _SCHEMA_LOCATION,
        },
    )

    identifier = ET.SubElement(
        resource,
        f"{{{_DATACITE_NS}}}identifier",
        {"identifierType": "DOI"},
    )
    identifier.text = r.identifier

    creators = ET.SubElement(resource, f"{{{_DATACITE_NS}}}creators")
    for name in r.creators:
        creator = ET.SubElement(creators, f"{{{_DATACITE_NS}}}creator")
        creator_name = ET.SubElement(creator, f"{{{_DATACITE_NS}}}creatorName")
        creator_name.text = name

    titles = ET.SubElement(resource, f"{{{_DATACITE_NS}}}titles")
    title = ET.SubElement(titles, f"{{{_DATACITE_NS}}}title")
    title.text = r.title

    publisher = ET.SubElement(resource, f"{{{_DATACITE_NS}}}publisher")
    publisher.text = r.publisher

    publication_year = ET.SubElement(resource, f"{{{_DATACITE_NS}}}publicationYear")
    publication_year.text = str(r.publication_year)

    resource_type = ET.SubElement(
        resource,
        f"{{{_DATACITE_NS}}}resourceType",
        {"resourceTypeGeneral": "Dataset"},
    )
    resource_type.text = r.resource_type

    body = ET.tostring(resource, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{body}'

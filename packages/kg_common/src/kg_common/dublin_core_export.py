"""Paper metadata -> simple Dublin Core (OAI-DC) XML — экспорт метаданных (§22).

A pure-stdlib serialiser that turns a document/paper *metadata dict* into
**simple Dublin Core** (``oai_dc``) XML — the interoperability format consumed
by OAI-PMH harvesters and institutional repositories. It is deliberately
distinct from DataCite (DOI registration) and BibTeX (LaTeX bibliographies):
OAI-DC is the lowest-common-denominator record every repository speaks —
формат для сбора метаданных репозиториями.

The vocabulary is the fifteen-element **Dublin Core Metadata Element Set**
(DC15): ``contributor``, ``coverage``, ``creator``, ``date``, ``description``,
``format``, ``identifier``, ``language``, ``publisher``, ``relation``,
``rights``, ``source``, ``subject``, ``title`` and ``type``. Any other term is
rejected — только термины DC15.

A :class:`DublinCoreRecord` holds an **ordered** tuple of ``(term, value)``
pairs (repetition allowed — two authors -> two ``dc:creator`` pairs).
:func:`from_paper` maps a metadata dict onto those pairs, dropping absent
fields; :func:`to_xml` renders the ``<oai_dc:dc>`` element, one
``<dc:term>value</dc:term>`` child per pair, XML-escaped and in tuple order.

Everything here is side-effect free: no I/O, no wall-clock, no globals, and the
mapping is deterministic and hand-checkable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape

__all__ = [
    "DC15_TERMS",
    "DublinCoreRecord",
    "from_paper",
    "to_xml",
]

#: The fifteen Dublin Core Metadata Element Set terms — набор DC15 (§22).
DC15_TERMS: frozenset[str] = frozenset(
    {
        "contributor",
        "coverage",
        "creator",
        "date",
        "description",
        "format",
        "identifier",
        "language",
        "publisher",
        "relation",
        "rights",
        "source",
        "subject",
        "title",
        "type",
    }
)

#: XML namespace URIs for the ``oai_dc`` container and the ``dc`` vocabulary.
_NS_OAI_DC: str = "http://www.openarchives.org/OAI/2.0/oai_dc/"
_NS_DC: str = "http://purl.org/dc/elements/1.1/"


# --------------------------------------------------------------------------- #
# Record — запись Dublin Core                                                  #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class DublinCoreRecord:
    """An ordered simple Dublin Core record — упорядоченная запись DC (§22).

    ``elements`` is a tuple of ``(term, value)`` pairs in emission order. Terms
    must belong to :data:`DC15_TERMS`; an unknown term raises :class:`ValueError`
    at construction. Repetition is allowed and meaningful (two ``creator`` pairs
    render as two ``dc:creator`` elements). Frozen value object; :meth:`as_dict`
    gives the canonical, round-trippable mapping.
    """

    elements: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        """Validate every term is a DC15 element — проверка терминов (§22)."""
        for term, _value in self.elements:
            if term not in DC15_TERMS:
                raise ValueError(f"unknown Dublin Core term: {term!r}")

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict view keyed by ``elements`` — сериализуемое представление.

        ``as_dict()['elements']`` is a list of ``[term, value]`` pairs preserving
        order, so it round-trips back through :class:`DublinCoreRecord` (after
        re-tupling) to an equal record.
        """
        return {"elements": [list(pair) for pair in self.elements]}


# --------------------------------------------------------------------------- #
# Build — построение записи из метаданных                                      #
# --------------------------------------------------------------------------- #


def _authors(meta: dict[str, Any]) -> list[str]:
    """Author names from ``authors`` (list/str) or ``author`` — список авторов.

    A string is treated as a single author; a sequence yields one name each.
    Missing -> empty list (no ``dc:creator`` pairs).
    """
    raw = meta.get("authors")
    if raw is None:
        raw = meta.get("author")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    return [str(name) for name in raw]


def from_paper(meta: dict[str, Any]) -> DublinCoreRecord:
    """Map a paper metadata dict onto a :class:`DublinCoreRecord` — построить.

    Field mapping (absent fields are dropped, no empty pairs):

    * ``title`` -> a single ``dc:title`` pair.
    * ``authors`` (list) / ``author`` -> one ``dc:creator`` pair **per** author.
    * ``year`` -> a single ``dc:date`` pair (stringified).
    * ``doi`` -> a single ``dc:identifier`` pair.
    * ``venue`` (falling back to ``journal``) -> a single ``dc:source`` pair.

    ``from_paper({})`` yields an empty-element record. Pairs are ordered
    title, creators, date, identifier, source.
    """
    pairs: list[tuple[str, str]] = []
    title = meta.get("title")
    if title:
        pairs.append(("title", str(title)))
    for name in _authors(meta):
        pairs.append(("creator", name))
    year = meta.get("year")
    if year is not None:
        pairs.append(("date", str(year)))
    doi = meta.get("doi")
    if doi:
        pairs.append(("identifier", str(doi)))
    venue = meta.get("venue") or meta.get("journal")
    if venue:
        pairs.append(("source", str(venue)))
    return DublinCoreRecord(elements=tuple(pairs))


# --------------------------------------------------------------------------- #
# Serialise — сериализация в XML                                              #
# --------------------------------------------------------------------------- #


def to_xml(r: DublinCoreRecord) -> str:
    """Render a record as an ``<oai_dc:dc>`` XML element — сериализация (§22).

    The root ``<oai_dc:dc>`` declares the ``oai_dc`` and ``dc`` namespace
    prefixes; each element becomes one ``<dc:term>value</dc:term>`` child in
    ``elements`` tuple order. Values are XML-escaped (``<`` -> ``&lt;``, ``&``
    -> ``&amp;``, ``>`` -> ``&gt;``). The output parses via
    :mod:`xml.etree.ElementTree`. An empty record -> just the root element.
    """
    lines = [
        f'<oai_dc:dc xmlns:oai_dc="{_NS_OAI_DC}" xmlns:dc="{_NS_DC}">',
    ]
    for term, value in r.elements:
        lines.append(f"  <dc:{term}>{escape(value)}</dc:{term}>")
    lines.append("</oai_dc:dc>")
    return "\n".join(lines)

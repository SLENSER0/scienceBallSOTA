"""Paper metadata -> CSL-JSON reference items — экспорт цитат в CSL-JSON (§22.6).

A pure-stdlib serialiser that turns paper *metadata dicts* into **CSL-JSON**
(Citation Style Language JSON) — the interchange format consumed by Zotero,
pandoc and citeproc. The repo already ships BibTeX (:mod:`bibtex_export`) and
RIS (:mod:`ris_export`) exporters; this adds the third common target so a
curated corpus reference list can be dropped straight into a CSL pipeline —
формат обмена библиографией.

CSL-JSON is an array of item objects. Each item carries an ``id``, a ``type``
(here ``article-journal``), a ``title``, an ``author`` array of ``{"family",
"given"}`` name parts, an ``issued`` date wrapped as ``{"date-parts":
[[year]]}``, an optional ``DOI`` and an optional ``container-title`` (the
venue/journal). Absent fields are **omitted entirely** — a missing ``doi``
produces no ``DOI`` key, никаких пустых полей.

Everything here is side-effect free: no I/O, no wall-clock, no globals. The
mapping is deterministic (``papers_to_csl_json`` uses ``sort_keys``) and
hand-checkable.

Public API:

* :class:`CslItem` — frozen CSL item with :meth:`as_dict` (canonical shape).
* :func:`split_name` — split ``"Last, First"``/``"First Last"`` into name parts.
* :func:`paper_to_csl` — build one :class:`CslItem` from a metadata dict.
* :func:`papers_to_csl_json` — serialise many metadata dicts to a CSL-JSON array.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "CslItem",
    "split_name",
    "paper_to_csl",
    "papers_to_csl_json",
]

#: CSL reference type emitted for every paper — тип ссылки CSL (§22.6).
_CSL_TYPE: str = "article-journal"


# --------------------------------------------------------------------------- #
# Name parsing — разбор имени автора                                           #
# --------------------------------------------------------------------------- #


def split_name(name: str) -> dict[str, str]:
    """Split an author name into CSL ``{"family", "given"}`` parts — разбор имени.

    Two input shapes are recognised (both hand-checkable):

    * ``"Last, First"`` (comma form) -> family is the text before the comma,
      given the text after — ``"Smith, John"`` -> ``{"family": "Smith",
      "given": "John"}``.
    * ``"First Last"`` (space form) -> the **last** whitespace-separated token is
      the family name, everything before it the given name — ``"John Smith"`` ->
      ``{"family": "Smith", "given": "John"}``.

    A single token yields a ``family`` with no ``given`` key; an empty string
    yields an empty ``family``. Surrounding whitespace is stripped.
    """
    text = name.strip()
    if "," in text:
        family, _, given = text.partition(",")
        parts = {"family": family.strip()}
        given = given.strip()
        if given:
            parts["given"] = given
        return parts
    tokens = text.split()
    if len(tokens) <= 1:
        return {"family": text}
    return {"family": tokens[-1], "given": " ".join(tokens[:-1])}


# --------------------------------------------------------------------------- #
# Item — элемент CSL-JSON                                                       #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class CslItem:
    """One CSL-JSON reference item — один элемент CSL-JSON (§22.6).

    Fields mirror the canonical CSL shape: ``id`` (citation key), ``type``
    (``article-journal``), ``title``, an ``author`` tuple of name-part dicts,
    ``issued_year`` (the publication year, or ``None``), ``doi`` and
    ``container_title`` (the venue). Frozen value object;
    :meth:`as_dict` renders the canonical, omission-aware mapping.
    """

    id: str
    type: str
    title: str
    author: tuple[dict[str, str], ...]
    issued_year: int | None
    doi: str | None
    container_title: str | None

    def as_dict(self) -> dict[str, Any]:
        """Return the canonical CSL-JSON mapping — каноническое представление CSL.

        Always includes ``id``, ``type`` and ``title``. ``author`` is emitted as
        a list of ``{"family", "given"}`` dicts only when non-empty. ``issued``
        is wrapped as ``{"date-parts": [[year]]}`` when a year is present.
        ``DOI`` and ``container-title`` appear only when their values are set —
        absent fields are omitted entirely (a missing ``doi`` -> no ``DOI`` key).
        """
        item: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "title": self.title,
        }
        if self.author:
            item["author"] = [dict(part) for part in self.author]
        if self.issued_year is not None:
            item["issued"] = {"date-parts": [[self.issued_year]]}
        if self.doi is not None:
            item["DOI"] = self.doi
        if self.container_title is not None:
            item["container-title"] = self.container_title
        return item


# --------------------------------------------------------------------------- #
# Build — построение элемента из метаданных                                    #
# --------------------------------------------------------------------------- #


def _authors(meta: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    """Author name parts from ``authors`` (list/str) or ``author`` — авторы.

    A string is treated as a single author; a sequence yields one entry per
    name. Each name is run through :func:`split_name`.
    """
    raw = meta.get("authors")
    if raw is None:
        raw = meta.get("author")
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (split_name(raw),)
    return tuple(split_name(str(name)) for name in raw)


def _year(meta: Mapping[str, Any]) -> int | None:
    """Coerce ``year`` to an ``int`` (or ``None``) — год издания (§22.6)."""
    raw = meta.get("year")
    if raw is None:
        return None
    return int(raw)


def paper_to_csl(meta: Mapping[str, Any]) -> CslItem:
    """Build a :class:`CslItem` from a paper metadata dict — построить элемент.

    The ``id`` is taken from ``id``/``doc_id`` (stringified, empty when absent);
    the ``type`` is always ``article-journal``. ``venue`` (falling back to
    ``journal``) maps to ``container_title``; ``doi`` maps to ``DOI``. Missing
    optional values become ``None`` and are dropped by :meth:`CslItem.as_dict`.
    """
    ident = meta.get("id")
    if ident is None:
        ident = meta.get("doc_id")
    venue = meta.get("venue") or meta.get("journal")
    doi = meta.get("doi")
    title = meta.get("title")
    return CslItem(
        id="" if ident is None else str(ident),
        type=_CSL_TYPE,
        title="" if title is None else str(title),
        author=_authors(meta),
        issued_year=_year(meta),
        doi=None if doi is None else str(doi),
        container_title=None if venue is None else str(venue),
    )


def papers_to_csl_json(metas: Sequence[Mapping[str, Any]]) -> str:
    """Serialise many metadata dicts to a CSL-JSON array — много ссылок в CSL.

    Each dict is mapped via :func:`paper_to_csl` and :meth:`CslItem.as_dict`,
    then the whole list is ``json.dumps``-ed with ``sort_keys=True`` for
    deterministic, byte-stable output. Empty input yields ``"[]"``.
    """
    items = [paper_to_csl(meta).as_dict() for meta in metas]
    return json.dumps(items, sort_keys=True)

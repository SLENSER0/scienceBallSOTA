"""Paper metadata -> RIS reference records — экспорт цитат в RIS (§22.6).

A pure-python serialiser that emits RIS-format reference records from the same
paper *metadata dicts* used elsewhere, so a curated reference list can be
imported into Zotero / EndNote / Mendeley. RIS is a tagged line format: each
record is a sequence of ``XX  - value`` lines (a two-letter tag code, **two
spaces**, a dash, a space, then the value), opened by a ``TY`` type line and
terminated by a bare ``ER  - `` line — формат тегированных строк.

Everything here is side-effect free: no I/O, no wall-clock, no globals. The
mapping is deterministic and hand-checkable.

Metadata contract (paper dict, все поля необязательны кроме смысла):

* ``type``    -> ``TY`` (mapped to a RIS reference type; ``paper`` -> ``JOUR``);
* ``authors`` -> one ``AU`` line **per author**, in input order;
* ``title``   -> ``TI``;
* ``year``    -> ``PY`` (stringified);
* ``doi``     -> ``DO`` (omitted entirely when absent — no empty ``DO`` line).

Public API:

* :class:`RisRecord` — frozen record wrapping an ordered tuple of ``(code,
  value)`` pairs, with :meth:`as_dict` and :meth:`to_ris`.
* :func:`paper_to_record` — build one :class:`RisRecord` from a metadata dict.
* :func:`records_to_ris` — serialise many metadata dicts to one RIS string.
* :func:`parse_ris` — parse an RIS string back into records (round-trip).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "RisRecord",
    "paper_to_record",
    "records_to_ris",
    "parse_ris",
]

#: RIS type code opening a record — код типа, открывающий запись.
_TY: str = "TY"
#: RIS end-of-record sentinel tag — тег конца записи.
_ER: str = "ER"
#: Separator between a tag code and its value: two spaces, dash, space.
_SEP: str = "  - "

#: meta ``type`` -> RIS reference type code — сопоставление типов (§22.6).
_TYPE_MAP: dict[str, str] = {
    "paper": "JOUR",
    "article": "JOUR",
    "journal": "JOUR",
    "book": "BOOK",
    "chapter": "CHAP",
    "conference": "CONF",
    "report": "RPRT",
    "thesis": "THES",
    "dataset": "DATA",
}
#: Fallback RIS type when ``type`` is unknown/missing — тип по умолчанию.
_DEFAULT_TYPE: str = "GEN"


# --------------------------------------------------------------------------- #
# Record — запись RIS                                                          #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RisRecord:
    """One RIS reference record — одна запись RIS (§22.6).

    ``tags`` is an ordered tuple of ``(code, value)`` pairs. A well-formed
    record starts with a ``TY`` tag and ends with the ``ER`` sentinel
    (``("ER", "")``); :func:`paper_to_record` always produces such records.
    """

    tags: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return the record as a mapping — запись как словарь.

        The ``tags`` are exposed as a list of ``[code, value]`` pairs, keeping
        order and duplicate codes (e.g. multiple ``AU`` authors) intact.
        """
        return {"tags": [[code, value] for code, value in self.tags]}

    def to_ris(self) -> str:
        """Render the record as RIS text — сериализовать запись в RIS.

        Each tag becomes one ``"XX  - value"`` line (tag, two spaces, dash,
        space, value); lines are joined by ``"\\n"``. The record is terminated
        by a bare ``"ER  - "`` line: if ``tags`` does not already end with an
        ``ER`` tag one is appended, so the output always closes correctly.
        """
        pairs: list[tuple[str, str]] = list(self.tags)
        if not pairs or pairs[-1][0] != _ER:
            pairs.append((_ER, ""))
        return "\n".join(f"{code}{_SEP}{value}" for code, value in pairs)


# --------------------------------------------------------------------------- #
# Build — построение записи из метаданных                                      #
# --------------------------------------------------------------------------- #


def _ris_type(meta: Mapping[str, Any]) -> str:
    """Map a metadata ``type`` to a RIS type code — тип записи RIS."""
    raw = meta.get("type")
    if raw is None:
        return _DEFAULT_TYPE
    return _TYPE_MAP.get(str(raw).strip().lower(), _DEFAULT_TYPE)


def paper_to_record(meta: Mapping[str, Any]) -> RisRecord:
    """Build a :class:`RisRecord` from a paper metadata dict — построить запись.

    Tag order is stable and hand-checkable: ``TY`` first, then one ``AU`` per
    author (input order), ``TI``, ``PY``, an optional ``DO`` (omitted when the
    ``doi`` is absent or ``None``), and finally the ``ER`` sentinel. Values are
    stringified; ``year`` renders as its decimal string (e.g. ``2020`` ->
    ``"2020"``).
    """
    tags: list[tuple[str, str]] = [(_TY, _ris_type(meta))]

    authors = meta.get("authors")
    if authors is not None:
        for author in authors:
            tags.append(("AU", str(author)))

    title = meta.get("title")
    if title is not None:
        tags.append(("TI", str(title)))

    year = meta.get("year")
    if year is not None:
        tags.append(("PY", str(year)))

    doi = meta.get("doi")
    if doi is not None:
        tags.append(("DO", str(doi)))

    tags.append((_ER, ""))
    return RisRecord(tags=tuple(tags))


def records_to_ris(metas: Sequence[Mapping[str, Any]]) -> str:
    """Serialise many metadata dicts to one RIS string — много записей в RIS.

    Each dict is mapped via :func:`paper_to_record` and rendered with
    :meth:`RisRecord.to_ris`; records are separated by a blank line. Every
    record ends with an ``"ER  - "`` line, so the boundaries are unambiguous.
    Empty input yields ``""``.
    """
    blocks = [paper_to_record(meta).to_ris() for meta in metas]
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------- #
# Parse — разбор RIS (round-trip)                                             #
# --------------------------------------------------------------------------- #


def _parse_line(line: str) -> tuple[str, str] | None:
    """Parse one ``"XX  - value"`` line into ``(code, value)`` — разбор строки.

    Returns ``None`` for blank lines (record separators). A line must contain
    the ``"  - "`` separator after a two-letter tag code to be a tag line.
    """
    if not line.strip():
        return None
    sep_at = line.find(_SEP)
    if sep_at != 2:
        return None
    code = line[:2]
    value = line[sep_at + len(_SEP) :]
    return code, value


def parse_ris(text: str) -> list[RisRecord]:
    """Parse an RIS string into records — разобрать RIS в записи (round-trip).

    Lines are read in order; a ``TY`` tag opens a new record and an ``ER`` tag
    (with any value) closes it. Blank lines between records are ignored. This is
    the inverse of :meth:`RisRecord.to_ris`: ``parse_ris(rec.to_ris())`` yields
    a single record whose ``tags`` equal ``rec.tags`` (given a well-formed
    ``TY``-opened, ``ER``-closed record).
    """
    records: list[RisRecord] = []
    current: list[tuple[str, str]] = []
    open_record = False

    for line in text.split("\n"):
        parsed = _parse_line(line)
        if parsed is None:
            continue
        code, _value = parsed
        if code == _TY:
            current = [parsed]
            open_record = True
        elif code == _ER:
            current.append(parsed)
            records.append(RisRecord(tags=tuple(current)))
            current = []
            open_record = False
        elif open_record:
            current.append(parsed)

    if open_record and current:
        records.append(RisRecord(tags=tuple(current)))
    return records

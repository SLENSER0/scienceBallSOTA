"""Paper metadata -> BibTeX ``@article`` export — экспорт списка литературы (§22.6).

A pure-Python, dependency-free serialiser that turns Paper/source metadata dicts
(``{doc_id/id, title, authors, year, doi, venue}``) into BibTeX ``@article``
entries for exporting a corpus reference list — ссылки для выгрузки корпуса.

Cite keys are **deterministic**: ``{firstauthorlastname}{year}`` lowercased and
ASCII-folded (Cyrillic/diacritics stripped to bare latin), so the same paper
always yields the same key. Colliding keys within one export are disambiguated by
:func:`dedupe_keys`, which appends ``a``/``b``/… suffixes — устранение коллизий.

Field values are escaped for BibTeX (``{``, ``}``, ``&`` -> ``\\{``, ``\\}``,
``\\&``) and wrapped in braces. Only fields present in the metadata are emitted
(a missing ``doi`` produces no ``doi`` line). Empty input -> ``""``.
"""

from __future__ import annotations

import dataclasses
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any

__all__ = [
    "BibEntry",
    "paper_to_entry",
    "papers_to_bibtex",
    "dedupe_keys",
]

# BibTeX-significant characters that must be backslash-escaped in a field value.
_ESCAPES = (("&", r"\&"), ("{", r"\{"), ("}", r"\}"))


@dataclass(frozen=True)
class BibEntry:
    """One BibTeX entry — ключ, тип и поля (§22.6).

    ``key`` is the cite key, ``entry_type`` the BibTeX type (``"article"``) and
    ``fields`` an ordered mapping of already-escaped field values. Frozen so an
    entry is a value object; :func:`dedupe_keys` produces re-keyed copies rather
    than mutating in place.
    """

    key: str
    entry_type: str
    fields: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict view — сериализуемое представление (key/entry_type/fields)."""
        return {
            "key": self.key,
            "entry_type": self.entry_type,
            "fields": dict(self.fields),
        }

    def to_bibtex(self) -> str:
        """Render the ``@<type>{key, ...}`` block (§22.6).

        Starts with ``@{entry_type}{{{key},`` and ends with a closing ``}`` on its
        own line; each field is one ``  name = {value}`` line, joined by commas.
        With no fields the block is just ``@type{key,\\n}``.
        """
        lines = [f"  {name} = {{{value}}}" for name, value in self.fields.items()]
        body = ",\n".join(lines)
        return f"@{self.entry_type}{{{self.key},\n{body}\n}}"


def _ascii_fold(value: str) -> str:
    """Strip diacritics/non-ASCII -> bare latin — приведение к ASCII."""
    normalised = unicodedata.normalize("NFKD", value)
    return normalised.encode("ascii", "ignore").decode("ascii")


def _authors(meta: dict[str, Any]) -> list[str]:
    """Author names from ``authors`` (list or str) or ``author`` — список авторов."""
    raw = meta.get("authors")
    if raw is None:
        raw = meta.get("author")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    return [str(name) for name in raw]


def _lastname(name: str) -> str:
    """Family name from ``"Last, First"`` or ``"First Last"`` — фамилия автора."""
    if "," in name:
        return name.split(",", 1)[0].strip()
    parts = name.split()
    return parts[-1] if parts else name.strip()


def _cite_key(meta: dict[str, Any]) -> str:
    """Deterministic ``{firstauthorlastname}{year}`` cite key (§22.6).

    The first author's family name is ASCII-folded, lowercased and reduced to
    ``[a-z0-9]``; the year is appended verbatim. With no author the stem is
    ``"anon"`` — например, ``{"author": "Smith, J.", "year": 2020}`` -> ``smith2020``.
    """
    authors = _authors(meta)
    stem = _lastname(authors[0]) if authors else "anon"
    stem = "".join(ch for ch in _ascii_fold(stem).lower() if ch.isalnum()) or "anon"
    year = meta.get("year")
    return f"{stem}{year}" if year is not None else stem


def _escape(value: str) -> str:
    """Escape BibTeX-special chars ``&``, ``{``, ``}`` — экранирование (§22.6)."""
    out = value
    for char, replacement in _ESCAPES:
        out = out.replace(char, replacement)
    return out


def paper_to_entry(meta: dict[str, Any]) -> BibEntry:
    """Build a :class:`BibEntry` from one metadata dict (§22.6).

    Emits only the fields present in ``meta`` (a missing ``doi``/``venue`` yields
    no line). Multiple authors are joined with ``" and "`` per BibTeX convention;
    ``venue`` maps to the ``journal`` field. Values are :func:`_escape`-d.
    """
    fields: dict[str, str] = {}
    authors = _authors(meta)
    if authors:
        fields["author"] = _escape(" and ".join(authors))
    title = meta.get("title")
    if title:
        fields["title"] = _escape(str(title))
    venue = meta.get("venue") if meta.get("venue") else meta.get("journal")
    if venue:
        fields["journal"] = _escape(str(venue))
    year = meta.get("year")
    if year is not None:
        fields["year"] = _escape(str(year))
    doi = meta.get("doi")
    if doi:
        fields["doi"] = _escape(str(doi))
    return BibEntry(key=_cite_key(meta), entry_type="article", fields=fields)


def _suffix(index: int) -> str:
    """0->``a``, 1->``b`` … base-26 suffix for collision disambiguation."""
    letters = ""
    index += 1  # 1-based so 26 stays single-letter "z", 27 -> "aa".
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("a") + remainder) + letters
    return letters


def dedupe_keys(entries: list[BibEntry]) -> list[BibEntry]:
    """Disambiguate colliding cite keys with ``a``/``b``/… suffixes (§22.6).

    Only keys shared by two or more entries are suffixed (in list order); unique
    keys are left untouched. Frozen entries are copied via
    :func:`dataclasses.replace` — два ``smith2020`` -> ``smith2020a`` и ``smith2020b``.
    """
    counts = Counter(entry.key for entry in entries)
    seen: dict[str, int] = {}
    result: list[BibEntry] = []
    for entry in entries:
        if counts[entry.key] > 1:
            index = seen.get(entry.key, 0)
            seen[entry.key] = index + 1
            result.append(dataclasses.replace(entry, key=entry.key + _suffix(index)))
        else:
            result.append(entry)
    return result


def papers_to_bibtex(metas: list[dict[str, Any]]) -> str:
    """Serialise many metadata dicts to a BibTeX document (§22.6).

    Each dict becomes an entry via :func:`paper_to_entry`; keys are de-duplicated
    with :func:`dedupe_keys` and blocks are separated by a blank line. Empty input
    yields ``""`` — пустой список -> пустая строка.
    """
    entries = dedupe_keys([paper_to_entry(meta) for meta in metas])
    return "\n\n".join(entry.to_bibtex() for entry in entries)

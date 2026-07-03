"""Document-level metadata extractor — DOI/authors/journal/year/title (§5.7).

Извлечение метаданных уровня документа: DOI, авторы, журнал, год, заголовок.

Mines §5.7 document-level metadata from parsed markdown/plain text. The result
feeds ``ParsedDocument.meta`` and informs the Document-vs-Paper label choice
(a surface with a DOI, authors and a journal reads as a *Paper*; a bare note
without any of them stays a plain *Document*).

Everything here is stdlib-only and fully deterministic:

- :func:`extract_doi` — first ``10.\\d{4,9}/\\S+`` match, with trailing
  sentence punctuation (``.``, ``,``, ``;`` …) and wrapping brackets stripped.
- :func:`extract_year` — first 4-digit year in the plausible ``1970..2049``
  publication window.
- :func:`extract_authors` — a byline splitter for ``Surname A., Surname B.``
  style lists (one or more initials per name, EN/RU surnames, hyphenated ok).
- :func:`extract_title` / :func:`extract_journal` — labelled or heading-based
  lookups, falling back to ``title_hint`` for the title.
- :func:`extract_doc_metadata` — the aggregate entry point returning a frozen
  :class:`DocMeta`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Patterns (§5.7)
# ---------------------------------------------------------------------------
# DOI core per the DOI syntax: ``10.`` + a 4–9 digit registrant + ``/`` + a
# suffix run of non-whitespace. The suffix is greedy, so trailing sentence
# punctuation is trimmed afterwards by :data:`_DOI_TRAIL`.
_DOI_RE = re.compile(r"10\.\d{4,9}/\S+")
# Trailing characters that belong to the surrounding prose, not the DOI itself.
_DOI_TRAIL = ".,;:!?)]}>\"'"

# Publication year window: 1970–2049, not glued to another digit on either side.
_YEAR_RE = re.compile(r"(?<!\d)(19[7-9]\d|20[0-4]\d)(?!\d)")

# One byline author: ``Surname`` (EN/RU, optionally hyphenated) then 1–3
# space/dot separated initials, e.g. ``Ivanov A.``, ``Van-Der A.B.``.
_AUTHOR_RE = re.compile(
    r"[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё]+(?:-[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё]+)?"
    r"\s+(?:[A-ZА-ЯЁ]\.\s*){1,3}"
)

# Labelled-line lookups, case-insensitive, value is the rest of the line.
_TITLE_LABEL = re.compile(r"^\s*title\s*[:.\-]\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_MD_H1 = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
_JOURNAL_LABEL = re.compile(
    r"^\s*(?:journal\s*[:.\-]|published in\s)\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class DocMeta:
    """Document-level metadata mined from a parsed surface (§5.7).

    Метаданные уровня документа, извлечённые из разобранного текста.

    Fields
    ------
    title
        Best-guess document title, or ``None`` (заголовок).
    authors
        Ordered, de-duplicated author bylines (авторы).
    doi
        Canonical DOI without trailing punctuation, or ``None`` (DOI).
    year
        Publication year in ``1970..2049``, or ``None`` (год).
    journal
        Journal / venue name, or ``None`` (журнал).
    """

    title: str | None
    authors: tuple[str, ...]
    doi: str | None
    year: int | None
    journal: str | None

    def as_dict(self) -> dict[str, object]:
        """Structured view; ``authors`` is a plain ``list`` (все поля)."""
        return {
            "title": self.title,
            "authors": list(self.authors),
            "doi": self.doi,
            "year": self.year,
            "journal": self.journal,
        }


def extract_doi(text: str) -> str | None:
    """First DOI in ``text`` with trailing prose punctuation stripped, else ``None``.

    Первый DOI в тексте без хвостовой пунктуации, иначе ``None``.
    """
    match = _DOI_RE.search(text)
    if match is None:
        return None
    return match.group(0).rstrip(_DOI_TRAIL) or None


def extract_year(text: str) -> int | None:
    """First plausible publication year (``1970..2049``) in ``text``, else ``None``.

    Первый правдоподобный год публикации (``1970..2049``), иначе ``None``.
    """
    match = _YEAR_RE.search(text)
    return int(match.group(1)) if match else None


def extract_authors(text: str) -> tuple[str, ...]:
    """Ordered, de-duplicated ``Surname A.`` bylines found in ``text``.

    Упорядоченный, дедуплицированный список авторов вида ``Фамилия И.``.
    """
    seen: dict[str, None] = {}
    for match in _AUTHOR_RE.finditer(text):
        # Collapse inner whitespace so ``Ivanov A.`` and ``Ivanov  A.`` fold.
        name = " ".join(match.group(0).split())
        seen.setdefault(name, None)
    return tuple(seen)


def extract_title(text: str, title_hint: str | None = None) -> str | None:
    """In-text title (``Title:`` label or first ``# H1``), else ``title_hint``.

    Заголовок из текста (метка ``Title:`` или первый ``# H1``), иначе подсказка.
    """
    label = _TITLE_LABEL.search(text)
    if label is not None:
        return label.group(1).strip()
    heading = _MD_H1.search(text)
    if heading is not None:
        return heading.group(1).strip()
    return title_hint.strip() if title_hint else None


def extract_journal(text: str) -> str | None:
    """Journal name from a ``Journal:`` / ``Published in`` line, else ``None``.

    Название журнала из строки ``Journal:`` / ``Published in``, иначе ``None``.
    """
    match = _JOURNAL_LABEL.search(text)
    return match.group(1).strip() if match else None


def extract_doc_metadata(text: str, title_hint: str | None = None) -> DocMeta:
    """Aggregate §5.7 document metadata from ``text`` into a frozen :class:`DocMeta`.

    Сводит метаданные документа §5.7 в замороженный :class:`DocMeta`.
    """
    return DocMeta(
        title=extract_title(text, title_hint),
        authors=extract_authors(text),
        doi=extract_doi(text),
        year=extract_year(text),
        journal=extract_journal(text),
    )

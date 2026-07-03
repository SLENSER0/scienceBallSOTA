"""Section-heading classification for chunk-type routing (§5.9 / §9.2 Step 3).

Извлечение (§5) routes each chunk differently depending on *which part* of a paper
it came from: an ``abstract`` is summarised, ``methods`` feed the processing graph,
``results`` feed measurements, and ``references`` / ``acknowledgements`` are usually
dropped. Before that routing (§9.2 Step 3) we need to turn a raw heading — Russian
*or* English, often prefixed with section numbering like ``2.1`` — into a canonical
:class:`SectionKind`.

This module is pure Python, stdlib only (только стандартная библиотека, без I/O):

* :func:`classify_section` matches a single heading against RU+EN keyword tables
  case-insensitively, after stripping any leading numbering (``2.1 Methods`` →
  ``Methods``), and returns a frozen :class:`SectionLabel` with the winning keyword.
* :func:`classify_path` collapses a nested heading path (breadcrumb) to one
  :class:`SectionKind` by trusting the *last* meaningful (non-``other``) segment.

When a heading names two parts at once — ``Результаты и обсуждение`` (Results and
Discussion) — the keyword appearing *earliest* in the text wins, so combined
headings resolve to their leading section (``results`` here).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class SectionKind(StrEnum):
    """Canonical part of a paper a heading belongs to (раздел статьи), §5.9."""

    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    METHODS = "methods"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    REFERENCES = "references"
    ACKNOWLEDGEMENTS = "acknowledgements"
    OTHER = "other"


# --- keyword tables (метки разделов), RU + EN, lowercase --------------------
# Order matters only as a tie-break when two keywords match at the *same* offset;
# the primary key is the earliest position in the heading (см. classify_section).
_KEYWORDS: tuple[tuple[SectionKind, tuple[str, ...]], ...] = (
    (SectionKind.ABSTRACT, ("аннотация", "abstract")),
    (SectionKind.INTRODUCTION, ("введение", "introduction")),
    (SectionKind.METHODS, ("материалы и методы", "методика", "методы", "methods")),
    (SectionKind.RESULTS, ("результаты", "results")),
    (SectionKind.DISCUSSION, ("обсуждение", "discussion")),
    (SectionKind.CONCLUSION, ("выводы", "заключение", "conclusion")),
    (SectionKind.REFERENCES, ("список литературы", "references")),
    (SectionKind.ACKNOWLEDGEMENTS, ("благодарности", "acknowledgements")),
)

# Leading section numbering: ``2``, ``2.1``, ``3)``, ``1.2.3.`` followed by space
# (нумерация раздела). Requires trailing whitespace so tokens like ``40Х`` survive.
_NUMBERING_RE = re.compile(r"^\s*\d+(?:[.\-]\d+)*[.)]?\s+")


@dataclass(frozen=True)
class SectionLabel:
    """Classification of a single heading (метка раздела), §5.9.

    Fields
    ------
    title
        The original, unmodified heading text (исходный заголовок).
    kind
        The canonical :class:`SectionKind` (тип раздела); ``OTHER`` if no keyword
        matched.
    matched_keyword
        The lowercase keyword that decided ``kind`` (совпавшее ключевое слово), or
        ``None`` when ``kind`` is ``OTHER``.
    """

    title: str
    kind: SectionKind
    matched_keyword: str | None

    def as_dict(self) -> dict[str, object]:
        """Full structured view; ``kind`` as its plain str value (все поля)."""
        return {
            "title": self.title,
            "kind": self.kind.value,
            "matched_keyword": self.matched_keyword,
        }


def strip_numbering(title: str) -> str:
    """Drop a leading section number from *title* (убрать нумерацию), §5.9.

    ``'2.1 Materials and Methods'`` → ``'Materials and Methods'``. A number without
    trailing whitespace (e.g. inside ``'40Х steel'``) is left untouched.
    """
    return _NUMBERING_RE.sub("", title, count=1)


def classify_section(title: str) -> SectionLabel:
    """Classify a single heading into a :class:`SectionLabel` (§5.9).

    Matching is case-insensitive and runs on the heading with any leading numbering
    removed. Across all RU+EN keywords, the one appearing at the *earliest* offset
    wins (ties broken by table order), so a combined heading such as
    ``'Результаты и обсуждение'`` resolves to ``RESULTS``. With no match the result
    is ``OTHER`` and ``matched_keyword`` is ``None``.
    """
    haystack = strip_numbering(title).lower()

    best_pos: int | None = None
    best_kind = SectionKind.OTHER
    best_keyword: str | None = None
    for kind, keywords in _KEYWORDS:
        for keyword in keywords:
            pos = haystack.find(keyword)
            if pos == -1:
                continue
            if best_pos is None or pos < best_pos:
                best_pos = pos
                best_kind = kind
                best_keyword = keyword

    return SectionLabel(title=title, kind=best_kind, matched_keyword=best_keyword)


def classify_path(section_path: list[str]) -> SectionKind:
    """Classify a nested heading path to one :class:`SectionKind` (§9.2 Step 3).

    Each breadcrumb segment is classified with :func:`classify_section`. The *last*
    segment that is not ``OTHER`` wins (самый глубокий значимый раздел), since deeper
    headings are more specific than their parents. If every segment is ``OTHER`` (or
    the path is empty), the result is the first segment's kind — i.e. ``OTHER``.
    """
    if not section_path:
        return SectionKind.OTHER

    last_meaningful: SectionKind | None = None
    for segment in section_path:
        kind = classify_section(segment).kind
        if kind is not SectionKind.OTHER:
            last_meaningful = kind

    if last_meaningful is not None:
        return last_meaningful
    return classify_section(section_path[0]).kind

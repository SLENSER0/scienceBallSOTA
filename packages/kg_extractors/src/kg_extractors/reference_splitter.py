"""References-section splitter — locate and itemise a bibliography (§5.7).

Разбиение раздела «References»/«Список литературы» на отдельные записи.

Complements :mod:`kg_extractors.doc_metadata` by carving the reference list out
of a parsed surface and splitting it into individual, char-offset-anchored
entries. Everything here is stdlib-only and fully deterministic.

- :func:`find_references_block` — find the span from just after a
  ``References`` / ``Список литературы`` heading to end-of-text.
- :func:`split_references` — split a block into :class:`ReferenceEntry` items by
  leading numeric markers (``[1]``, ``1.``, ``12)``) when present, else by blank
  lines; whitespace is trimmed and empty entries dropped. Each entry keeps its
  ``char_start``/``char_end`` offsets *into the block* and its parsed ``marker``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Patterns (§5.7)
# ---------------------------------------------------------------------------
# A standalone references heading, EN or RU, on its own line.
_HEADING_RE = re.compile(
    r"^[ \t]*(?:#+[ \t]*)?(?:references|bibliography|список литературы"
    r"|литература)[ \t]*:?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)

# A leading numeric marker at the start of an entry: ``[1]``, ``1.`` or ``12)``.
# Group 1 captures the bare number (e.g. ``1``); the trailing separator is
# whitespace so the marker is followed by the entry text.
_MARKER_RE = re.compile(r"(?:\[(\d+)\]|(\d+)[.)])\s+", re.MULTILINE)
# Anchored variant to detect a marker exactly at a candidate line start.
_MARKER_AT = re.compile(r"^(?:\[(\d+)\]|(\d+)[.)])\s+")


@dataclass(frozen=True)
class ReferenceEntry:
    """One bibliography entry with its offsets into the block (§5.7).

    Одна библиографическая запись со смещениями внутри блока.

    Fields
    ------
    index
        Zero-based position within the list (порядковый номер).
    text
        Trimmed entry text without its leading marker (текст записи).
    marker
        Parsed numeric marker such as ``'1'``, or ``None`` (маркер).
    char_start, char_end
        Offsets of :attr:`text` within the source block (смещения).
    """

    index: int
    text: str
    marker: str | None
    char_start: int
    char_end: int

    def as_dict(self) -> dict[str, object]:
        """Structured view of the entry (все поля записи)."""
        return {
            "index": self.index,
            "text": self.text,
            "marker": self.marker,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


@dataclass(frozen=True)
class ReferenceList:
    """An ordered, immutable list of :class:`ReferenceEntry` items (§5.7).

    Упорядоченный неизменяемый список библиографических записей.
    """

    entries: tuple[ReferenceEntry, ...]

    def __len__(self) -> int:
        """Number of entries (число записей)."""
        return len(self.entries)

    def as_dict(self) -> dict[str, object]:
        """Structured view; ``entries`` is a plain ``list`` (все записи)."""
        return {"entries": [entry.as_dict() for entry in self.entries]}


def find_references_block(text: str) -> tuple[int, int] | None:
    """Span from just after a references heading to end-of-text, else ``None``.

    Диапазон от места сразу после заголовка списка литературы до конца текста.

    The returned ``start`` points at the first character *after* the heading
    line (its trailing newline is skipped), and ``end`` is ``len(text)``.
    """
    match = _HEADING_RE.search(text)
    if match is None:
        return None
    start = match.end()
    # Skip the single newline that terminates the heading line, if present.
    if start < len(text) and text[start] == "\n":
        start += 1
    return (start, len(text))


def _split_by_marker(block: str) -> list[ReferenceEntry] | None:
    """Split ``block`` by leading numeric markers, or ``None`` if none apply.

    Разбиение по числовым маркерам, либо ``None`` если их нет.
    """
    # Collect marker positions that sit at a line start (offset 0 or after \n).
    starts: list[tuple[int, str]] = []
    for match in _MARKER_RE.finditer(block):
        at_line_start = match.start() == 0 or block[match.start() - 1] == "\n"
        if not at_line_start:
            continue
        marker = match.group(1) or match.group(2)
        starts.append((match.start(), marker))
    if not starts:
        return None

    entries: list[ReferenceEntry] = []
    for pos, (marker_start, marker) in enumerate(starts):
        marker_end = starts[pos + 1][0] if pos + 1 < len(starts) else len(block)
        segment = block[marker_start:marker_end]
        head = _MARKER_AT.match(segment)
        # Offset of the entry text within the block, after the marker token.
        text_start = marker_start + (head.end() if head else 0)
        raw = block[text_start:marker_end]
        stripped = raw.strip()
        if not stripped:
            continue
        # Re-anchor the trimmed text to real block offsets.
        lead = len(raw) - len(raw.lstrip())
        char_start = text_start + lead
        char_end = char_start + len(stripped)
        entries.append(
            ReferenceEntry(
                index=len(entries),
                text=stripped,
                marker=marker,
                char_start=char_start,
                char_end=char_end,
            )
        )
    return entries


def _split_by_blank(block: str) -> list[ReferenceEntry]:
    """Fallback: split ``block`` on blank lines into markerless entries.

    Запасной вариант: разбиение по пустым строкам без маркеров.
    """
    entries: list[ReferenceEntry] = []
    cursor = 0
    for chunk in re.split(r"\n[ \t]*\n", block):
        chunk_start = cursor
        cursor += len(chunk) + 2  # account for the consumed blank-line separator
        stripped = chunk.strip()
        if not stripped:
            continue
        lead = len(chunk) - len(chunk.lstrip())
        char_start = chunk_start + lead
        char_end = char_start + len(stripped)
        entries.append(
            ReferenceEntry(
                index=len(entries),
                text=stripped,
                marker=None,
                char_start=char_start,
                char_end=char_end,
            )
        )
    return entries


def split_references(block: str) -> ReferenceList:
    """Split a references ``block`` into a :class:`ReferenceList` (§5.7).

    Разбиение блока списка литературы на :class:`ReferenceList`.

    Numeric markers (``[1]``, ``1.``, ``12)``) win when present; otherwise the
    block is split on blank lines. Whitespace is trimmed and empties dropped.
    """
    if not block.strip():
        return ReferenceList(entries=())
    by_marker = _split_by_marker(block)
    entries = by_marker if by_marker is not None else _split_by_blank(block)
    return ReferenceList(entries=tuple(entries))

"""Running header/footer (page furniture) detector (§5.7, §5.11).

Pure-python (standard-library only) детектор «мебели страницы» — running
headers, running footers and bare page numbers that repeat across many pages of
a parsed document. Такие строки повторяются на большинстве страниц и являются
шумом для чанкинга: they must be stripped before the §5.7 heading hierarchy is
built and before §5.11 clean-parse chunking, otherwise the same running title or
page number leaks into every chunk.

The detector groups pages by their *normalized* lines and flags any line whose
page-coverage fraction reaches ``min_fraction`` (default 0.6). A flagged line is
classified as ``page_number`` when its text is a bare page number
(``"12"``, «Стр. 3», «с. 4», ``Page 5``, ``- 6 -``) and otherwise as
``header_footer``. Each hit is a frozen :class:`Furniture` record carrying the
line text, the tuple of page numbers it appeared on and its ``kind``.

:func:`strip_furniture` removes exactly the flagged lines from the pages (по
нормализованному сравнению) and keeps every other line intact.

Kuzu note: derived furniture props are read via ``get_node()`` — they are NOT
queryable columns; RETURN base columns only. No external dependency.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

__all__ = ["Furniture", "detect_furniture", "strip_furniture"]

# Allowed classification labels (§5.7/§5.11).
KIND_HEADER_FOOTER = "header_footer"
KIND_PAGE_NUMBER = "page_number"

# A "bare page number" line: an optional RU/EN page marker («Стр.»/«с.»/``Page``/
# ``P.``) and/or dash/pipe decoration around a single integer, e.g. ``12``,
# «Стр. 3», «с. 4», ``Page 5``, ``- 6 -``, ``| 7 |``. Case-insensitive.
_PAGE_NUMBER_RE = re.compile(
    r"^[\s\-–—|]*"
    r"(?:(?:стр(?:аница)?|с|page|pp?)\.?\s*)?"
    r"\d+"
    r"[\s\-–—|]*$",
    re.IGNORECASE,
)


def _normalize(line: str) -> str:
    """Collapse internal whitespace and strip ends (нормализация строки)."""
    return re.sub(r"\s+", " ", line).strip()


def _is_page_number(line: str) -> bool:
    """True when ``line`` is a bare page number (RU+EN markers, decorations)."""
    text = _normalize(line)
    return bool(text) and _PAGE_NUMBER_RE.match(text) is not None


@dataclass(frozen=True)
class Furniture:
    """One repeated page-furniture line detected across pages (§5.7/§5.11).

    Fields
    ------
    line
        The normalized line text that repeats (нормализованный текст строки).
    pages
        Sorted tuple of page numbers on which the line appeared (номера
        страниц).
    kind
        ``"header_footer"`` or ``"page_number"`` (тип: колонтитул или номер).
    """

    line: str
    pages: tuple[int, ...]
    kind: str

    def as_dict(self) -> dict[str, object]:
        """Full structured view; ``pages`` is a list (все поля, pages -> list)."""
        return {"line": self.line, "pages": list(self.pages), "kind": self.kind}


def detect_furniture(
    pages: list[tuple[int, str]],
    min_fraction: float = 0.6,
) -> list[Furniture]:
    """Detect running headers/footers and page numbers across ``pages``.

    Определяет строки-«мебель», повторяющиеся минимум на ``min_fraction`` доле
    страниц.

    Parameters
    ----------
    pages
        List of ``(page_number, page_text)`` pairs; ``page_text`` is split into
        lines internally (список пар «номер страницы, текст страницы»).
    min_fraction
        Minimum fraction of *distinct* pages a line must cover to be flagged
        (default 0.6, inclusive).

    Returns
    -------
    list[Furniture]
        Flagged lines ordered by kind (headers/footers first, then page
        numbers), then by descending coverage, then alphabetically. Empty input
        yields ``[]``.
    """
    if not pages:
        return []

    distinct_pages = {page_no for page_no, _ in pages}
    total = len(distinct_pages)
    threshold = min_fraction * total

    # Map normalized line -> set of page numbers it appeared on.
    line_pages: dict[str, set[int]] = defaultdict(set)
    for page_no, text in pages:
        for raw in text.splitlines():
            norm = _normalize(raw)
            if norm:
                line_pages[norm].add(page_no)

    results: list[Furniture] = []
    for norm, page_set in line_pages.items():
        if len(page_set) >= threshold:
            kind = KIND_PAGE_NUMBER if _is_page_number(norm) else KIND_HEADER_FOOTER
            results.append(Furniture(line=norm, pages=tuple(sorted(page_set)), kind=kind))

    # Deterministic order: header_footer before page_number, then by coverage
    # (desc), then alphabetically.
    kind_rank = {KIND_HEADER_FOOTER: 0, KIND_PAGE_NUMBER: 1}
    results.sort(key=lambda f: (kind_rank.get(f.kind, 2), -len(f.pages), f.line))
    return results


def strip_furniture(
    pages: list[tuple[int, str]],
    furniture: list[Furniture],
) -> list[tuple[int, str]]:
    """Remove flagged furniture lines from ``pages``, keeping all other lines.

    Удаляет ровно помеченные строки (по нормализованному сравнению), сохраняя
    остальные и их порядок. Blank-only pages are preserved as empty strings.

    Returns
    -------
    list[tuple[int, str]]
        New ``(page_number, cleaned_text)`` pairs in the original page order.
    """
    flagged = {f.line for f in furniture}
    cleaned: list[tuple[int, str]] = []
    for page_no, text in pages:
        kept = [raw for raw in text.splitlines() if _normalize(raw) not in flagged]
        cleaned.append((page_no, "\n".join(kept)))
    return cleaned

"""Evidence page-highlight span builder for §14.9 page-highlight payloads.

Построение подсветки цитат на странице документа (§14.9) — из символьных
смещений доказательств (§8.3) в диапазоны подсветки для ответа
``GET /documents/{doc_id}/pages/{page}``.

The §8.3 evidence records carry absolute character offsets into a page's
extracted text. Nothing existing turns those offsets into the highlight
payload the page endpoint returns, so this module provides the small pure
building blocks:

* :class:`HighlightSpan`   — frozen span ``[char_start, char_end)`` + sliced text.
* :func:`clamp_span`       — clamp offsets into ``[0, page_len]``, keep start<=end.
* :func:`build_highlight`  — build a clamped span and slice its page text.
* :func:`overlaps`         — do two spans on the same page intersect?

Offsets are treated as a half-open interval ``[char_start, char_end)`` so that
:attr:`text` equals ``page_text[char_start:char_end]`` and adjacent spans that
merely touch (``a.end == b.start``) do not count as overlapping.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HighlightSpan:
    """One highlighted evidence span on a page — ``[char_start, char_end)`` (§14.9).

    Инвариант: ``0 <= char_start <= char_end`` и ``text`` — срез текста страницы
    по этим смещениям. :meth:`as_dict` — вид для JSON-ответа/журналов.
    """

    page: int
    char_start: int
    char_end: int
    text: str

    def as_dict(self) -> dict[str, int | str]:
        """Structured view — ``page`` / ``char_start`` / ``char_end`` / ``text`` (§14.9)."""
        return {
            "page": self.page,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "text": self.text,
        }


def clamp_span(char_start: int, char_end: int, page_len: int) -> tuple[int, int]:
    """Clamp ``[char_start, char_end)`` into ``[0, page_len]`` with start<=end (§14.9).

    Ограничивает смещения границами страницы: каждый конец приводится в
    ``[0, page_len]``; если после этого ``start > end``, конец подтягивается к
    началу (пустой диапазон), чтобы инвариант ``start <= end`` всегда держался.
    """
    lo = 0 if page_len < 0 else page_len
    start = min(max(char_start, 0), lo)
    end = min(max(char_end, 0), lo)
    if end < start:
        end = start
    return start, end


def build_highlight(page: int, page_text: str, char_start: int, char_end: int) -> HighlightSpan:
    """Build a clamped :class:`HighlightSpan` and slice its page text (§14.9).

    Строит подсветку: смещения ограничиваются длиной ``page_text``, затем текст
    нарезается по итоговым границам, поэтому ``text`` всегда согласован со
    смещениями (даже при выходе исходных смещений за пределы страницы).
    """
    start, end = clamp_span(char_start, char_end, len(page_text))
    return HighlightSpan(
        page=page,
        char_start=start,
        char_end=end,
        text=page_text[start:end],
    )


def overlaps(a: HighlightSpan, b: HighlightSpan) -> bool:
    """Whether two spans lie on the same page and their intervals intersect (§14.9).

    Пересекаются ли подсветки: только на одной странице и при непустом
    пересечении полуоткрытых интервалов (соприкосновение концами — не
    пересечение).
    """
    if a.page != b.page:
        return False
    return a.char_start < b.char_end and b.char_start < a.char_end

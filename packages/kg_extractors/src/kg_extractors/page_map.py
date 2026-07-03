"""PDF page ↔ character-offset map — где в тексте кончается страница (§5.16).

When a PDF is flattened into one long character stream (the concatenated page
texts the extractors see), the page structure is lost: an offset like ``1_204``
no longer says *«page 3»*. :class:`PageMap` puts it back. Each page contributes
one half-open character span ``[char_start, char_end)`` into the flat text, and
the map answers the two questions the rest of the pipeline asks:

* :meth:`PageMap.page_for` — «which page owns this character offset?»
  (offset → page, ``None`` outside every span);
* :meth:`PageMap.span_for` — «where does this page live in the flat text?»
  (page → ``(start, end)``, ``None`` for an unknown page).

Spans are **half-open**: ``char_start`` is inclusive, ``char_end`` is exclusive,
so contiguous pages (page 1 ``[0, 10)``, page 2 ``[10, 20)``) share the boundary
offset ``10`` without ambiguity — it belongs to page 2. Spans may not overlap and
a page may be added only once; both are rejected at :meth:`PageMap.add_span` so
that :meth:`page_for` is always single-valued and hand-checkable. Insertion order
is preserved. Pure Python — stdlib only, no PDF library, no I/O.

Public API:

- :class:`PageMap` — mutable builder; :meth:`add_span`, :meth:`page_for`,
  :meth:`span_for`, and a frozen :meth:`as_dict` snapshot.
"""

from __future__ import annotations


class PageMap:
    """Character-offset ↔ page map over one flattened PDF text (§5.16).

    Build it by feeding one span per page with :meth:`add_span`, then query with
    :meth:`page_for` (offset → page) and :meth:`span_for` (page → span). Spans are
    half-open ``[char_start, char_end)``; they may not overlap and each page is
    added exactly once. Insertion order is preserved for :meth:`as_dict`.
    """

    __slots__ = ("_spans",)

    def __init__(self) -> None:
        # page → (char_start, char_end), in insertion order (порядок добавления).
        self._spans: dict[int, tuple[int, int]] = {}

    def add_span(self, page: int, char_start: int, char_end: int) -> None:
        """Register page ``page`` as the half-open span ``[char_start, char_end)``.

        Raises :class:`ValueError` when the offsets are malformed
        (``char_start < 0`` or ``char_end < char_start``), when ``page`` was
        already registered, or when the new span overlaps an existing one — each
        keeps :meth:`page_for` single-valued (однозначное сопоставление).
        """
        if char_start < 0:
            raise ValueError(f"char_start must be >= 0, got {char_start}")
        if char_end < char_start:
            raise ValueError(f"char_end {char_end} precedes char_start {char_start}")
        if page in self._spans:
            raise ValueError(f"page {page} already has a span {self._spans[page]}")
        for other, (start, end) in self._spans.items():
            # Two half-open ranges overlap iff each starts before the other ends.
            if char_start < end and start < char_end:
                raise ValueError(
                    f"span [{char_start}, {char_end}) for page {page} overlaps "
                    f"page {other} span [{start}, {end})"
                )
        self._spans[page] = (char_start, char_end)

    def page_for(self, offset: int) -> int | None:
        """Return the page whose span contains ``offset``, or ``None`` if none.

        ``offset`` is matched against the half-open span ``[start, end)``: the
        start is inclusive, the end exclusive. Offsets that fall in a gap between
        spans, before the first span, or past the last span yield ``None``
        (смещение вне всех страниц).
        """
        for page, (start, end) in self._spans.items():
            if start <= offset < end:
                return page
        return None

    def span_for(self, page: int) -> tuple[int, int] | None:
        """Return page ``page``'s ``(char_start, char_end)`` span, else ``None``.

        ``None`` is returned for a page that was never registered (неизвестная
        страница) rather than raising.
        """
        return self._spans.get(page)

    def as_dict(self) -> dict[str, object]:
        """Frozen structured snapshot (copy) — ``pages`` and ``n`` (§5.16).

        ``pages`` maps every registered ``page`` to a ``[char_start, char_end]``
        list in insertion order; ``n`` is the number of pages. The returned
        containers are fresh copies, so mutating the view never touches the map.
        """
        return {
            "pages": {page: [start, end] for page, (start, end) in self._spans.items()},
            "n": len(self._spans),
        }

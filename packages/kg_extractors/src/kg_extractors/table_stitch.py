"""Cross-page table stitching (§5.7).

Сшивание таблиц, разорванных между страницами PDF.

A single logical table often spills across a page break, emerging from the PDF
extractor as two (or more) fragments that share the *same* header row. This module
merges consecutive fragments — in page order — whose normalized headers are
identical, concatenating their rows into one :class:`StitchedTable`. A fragment with
different headers starts a fresh group.

Header normalization lowercases and trims each cell so cosmetic differences (a
trailing space, a stray capital) do not defeat the match — ``'M '`` and ``'m'``
stitch together.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StitchedTable:
    """A table assembled from one or more consecutive page fragments (§5.7).

    ``headers`` — the header cells (from the first fragment, verbatim); ``rows`` —
    the concatenated body rows in page order; ``page_start`` / ``page_end`` — the
    minimum / maximum source page numbers; ``source_count`` — how many fragments
    were merged (``1`` when the table sat on a single page).
    """

    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    page_start: int
    page_end: int
    source_count: int

    def as_dict(self) -> dict[str, object]:
        """Serialize to a plain ``dict`` with ``rows`` as a list of lists."""
        data = asdict(self)
        data["headers"] = list(self.headers)
        data["rows"] = [list(row) for row in self.rows]
        return data


def _normalize_headers(headers: list[str]) -> tuple[str, ...]:
    """Lowercase and trim each header cell for case/space-insensitive matching."""
    return tuple(str(cell).strip().lower() for cell in headers)


def stitch_tables(tables: list[dict]) -> list[StitchedTable]:
    """Stitch consecutive same-header table fragments into :class:`StitchedTable`\\ s.

    Сшить последовательные фрагменты таблиц с одинаковыми заголовками.

    Each input ``dict`` has ``headers: list[str]``, ``rows: list[list[str]]`` and
    ``page: int``. Fragments are processed in ascending page order; those with
    identical *normalized* headers and adjacent in that order merge (rows
    concatenated). A header mismatch opens a new group. Empty input yields ``[]``.
    """
    if not tables:
        return []

    ordered = sorted(tables, key=lambda t: t["page"])

    result: list[StitchedTable] = []
    cur_headers: tuple[str, ...] | None = None
    cur_norm: tuple[str, ...] | None = None
    cur_rows: list[tuple[str, ...]] = []
    cur_pages: list[int] = []
    cur_count = 0

    def _flush() -> None:
        if cur_headers is None:
            return
        result.append(
            StitchedTable(
                headers=cur_headers,
                rows=tuple(cur_rows),
                page_start=min(cur_pages),
                page_end=max(cur_pages),
                source_count=cur_count,
            )
        )

    for table in ordered:
        headers = list(table["headers"])
        norm = _normalize_headers(headers)
        rows = [tuple(str(cell) for cell in row) for row in table["rows"]]
        page = int(table["page"])

        if cur_norm is not None and norm == cur_norm:
            cur_rows.extend(rows)
            cur_pages.append(page)
            cur_count += 1
        else:
            _flush()
            cur_headers = tuple(headers)
            cur_norm = norm
            cur_rows = list(rows)
            cur_pages = [page]
            cur_count = 1

    _flush()
    return result

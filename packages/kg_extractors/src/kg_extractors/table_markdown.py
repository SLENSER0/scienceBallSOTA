"""Whole-table Markdown serialization for LLM / context windows (§5.9 / §5.7).

When a table has to be handed to an LLM or embedded in a prompt / context
window, a GitHub-style pipe table is the most robust, human-legible carrier: it
survives copy-paste, is trivially diffable, and every model has seen millions of
them. This module renders a header + rows pair into exactly such a table and,
crucially, can *invert* a well-formed one — so a table can round-trip through the
context and come back structured (заголовки → таблица → заголовки).

Rendering rules (:func:`to_markdown`):

* one header line, one ``---`` separator line, one line per data row;
* ragged rows shorter than ``n_cols`` are padded on the right with ``''``
  (короткие строки дополняются), longer rows are truncated to ``n_cols``
  (длинные строки обрезаются);
* an embedded pipe ``|`` inside a cell is escaped as ``\\|`` so it cannot break
  the column grid;
* with ``align=True`` every column is space-padded to a common width, giving a
  visually aligned grid (выравнивание по ширине столбца); with ``align=False``
  cells are emitted tight, which is what makes the round-trip exact.

Inversion (:func:`parse_markdown`) reads a well-formed pipe table back into
``(headers, rows)``, undoing the escaping and stripping alignment padding, and
skips the ``---`` separator line.

Pure Python — stdlib only, no LLM, no I/O.

Public API:

- :class:`MarkdownTable` — frozen render result with :meth:`MarkdownTable.as_dict`;
- :func:`to_markdown` — render ``(headers, rows)`` to a pipe table;
- :func:`parse_markdown` — invert a well-formed pipe table.
"""

from __future__ import annotations

from dataclasses import dataclass

_SEP = "---"


@dataclass(frozen=True)
class MarkdownTable:
    """A rendered GitHub-style pipe table (§5.9 / §5.7).

    Fields
    ------
    markdown
        The full table text: header line, ``---`` separator line, then one line
        per data row, joined by newlines (текст таблицы).
    n_rows
        Number of data rows rendered, excluding header and separator
        (число строк данных).
    n_cols
        Number of columns, taken from the header width (число столбцов).
    """

    markdown: str
    n_rows: int
    n_cols: int

    def as_dict(self) -> dict[str, object]:
        """Full structured view (all fields, JSON-friendly)."""
        return {
            "markdown": self.markdown,
            "n_rows": self.n_rows,
            "n_cols": self.n_cols,
        }


def _escape(cell: str) -> str:
    """Escape an embedded pipe so it cannot break the column grid (``|`` → ``\\|``)."""
    return str(cell).replace("|", "\\|")


def _unescape(cell: str) -> str:
    """Undo :func:`_escape` (``\\|`` → ``|``)."""
    return cell.replace("\\|", "|")


def _fit(row: list[str], n_cols: int) -> list[str]:
    """Pad a short row with ``''`` / truncate a long row to exactly ``n_cols``."""
    cells = [str(c) for c in row[:n_cols]]
    if len(cells) < n_cols:
        cells.extend([""] * (n_cols - len(cells)))
    return cells


def to_markdown(
    headers: list[str],
    rows: list[list[str]],
    align: bool = True,
) -> MarkdownTable:
    """Render ``(headers, rows)`` into a GitHub-style pipe table (§5.9 / §5.7).

    The column count ``n_cols`` is fixed by ``headers``. Every data row is fit to
    ``n_cols`` — short rows padded on the right with ``''``, long rows truncated
    (see :func:`_fit`) — and each cell has its embedded pipes escaped. With
    ``align=True`` columns are space-padded to a common width per column; with
    ``align=False`` cells are emitted tight (exact round-trip). The output always
    carries a header line and a ``---`` separator line, even for an empty
    ``rows`` (``n_rows == 0``).
    """
    n_cols = len(headers)
    head = [_escape(h) for h in headers]
    body = [[_escape(c) for c in _fit(row, n_cols)] for row in rows]

    if align:
        # Each column is at least ``len(_SEP)`` wide so the ``---`` row and every
        # data / header line share a common per-column width (равная ширина).
        widths = [max(len(head[c]), len(_SEP)) for c in range(n_cols)]
        for line in body:
            for c in range(n_cols):
                widths[c] = max(widths[c], len(line[c]))
        sep_cells = [_SEP.ljust(w, "-") for w in widths]
        head_cells = [head[c].ljust(widths[c]) for c in range(n_cols)]
        body_cells = [[cell.ljust(widths[c]) for c, cell in enumerate(line)] for line in body]
    else:
        sep_cells = [_SEP] * n_cols
        head_cells = head
        body_cells = body

    lines = [_join(head_cells), _join(sep_cells)]
    lines.extend(_join(line) for line in body_cells)
    return MarkdownTable(markdown="\n".join(lines), n_rows=len(rows), n_cols=n_cols)


def _join(cells: list[str]) -> str:
    """Wrap a rendered row in leading / trailing pipes with single-space padding."""
    return "| " + " | ".join(cells) + " |"


def _split(line: str) -> list[str]:
    """Split one pipe-table line into its cells, honouring ``\\|`` escapes."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|") and not stripped.endswith("\\|"):
        stripped = stripped[:-1]
    cells: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(stripped):
        ch = stripped[i]
        if ch == "\\" and i + 1 < len(stripped) and stripped[i + 1] == "|":
            buf.append("\\|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def _is_separator(cells: list[str]) -> bool:
    """True when every cell is a run of ``-`` (optionally ``:``-decorated) — a ``---`` row."""
    for cell in cells:
        core = cell.strip().strip(":")
        if not core or any(ch != "-" for ch in core):
            return False
    return True


def parse_markdown(md: str) -> tuple[list[str], list[list[str]]]:
    """Invert a well-formed pipe table back into ``(headers, rows)`` (§5.9 / §5.7).

    The first non-blank line is the header; the following ``---`` separator line
    is skipped; every remaining non-blank line becomes a data row. Cells are
    un-escaped (``\\|`` → ``|``) and alignment padding is stripped, so
    ``parse_markdown(to_markdown(...).markdown)`` round-trips exactly when the
    source rows are rectangular (``align`` need not match).
    """
    raw_lines = [ln for ln in md.splitlines() if ln.strip()]
    if not raw_lines:
        return [], []
    headers = [_unescape(c) for c in _split(raw_lines[0])]
    rows: list[list[str]] = []
    for line in raw_lines[1:]:
        cells = _split(line)
        if _is_separator(cells):
            continue
        rows.append([_unescape(c) for c in cells])
    return headers, rows

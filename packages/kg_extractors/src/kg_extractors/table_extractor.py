"""Table extraction from parsed documents → structured rows (§5.7).

Turns the two table shapes that survive Markdown/plaintext export of a parsed
document (таблицы из разобранных документов) into a single structured form:

- **Markdown pipe tables** — ``| материал | твёрдость |`` rows separated from
  the header by a ``--- | ---`` alignment row;
- **delimited tables** — TSV (tab-separated) or multi-space *aligned* columns,
  plus any explicit single-character separator (``,`` / ``;`` …).

Each table becomes a frozen :class:`ParsedTable` — ``headers`` + ``rows`` (a
list of ``header -> cell`` dicts) with ``n_rows`` / ``n_cols`` and a
``cell_at(row, col)`` accessor. RU headers (материал / твёрдость / …), empty
cells (пустые ячейки) and ragged rows (неровные строки — padded to ``n_cols``)
are all handled. :func:`extract_tables` walks a block of mixed prose + tables
and returns every table it finds together with its character span (позиция в
тексте).

Pure python — only :mod:`re` and :mod:`str`; deterministic, dependency-light.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "ParsedTable",
    "parse_markdown_table",
    "parse_delimited",
    "extract_tables",
]

# Sentinel standing in for the "runs of 2+ whitespace" (multi-space aligned)
# delimiter — it is not a literal separator string, so it needs its own token.
_MULTISPACE = "\x00multispace\x00"

# A Markdown alignment cell: dashes with optional leading/trailing colon
# (``---`` / ``:--`` / ``:-:`` …).
_SEP_CELL_RE = re.compile(r":?-{1,}:?")
# "non-space, 2+ spaces, non-space" — the fingerprint of a multi-space column gap.
_MULTISPACE_RE = re.compile(r"\S {2,}\S")


@dataclass(frozen=True)
class _Line:
    """One physical line with its absolute char span in the source text."""

    start: int
    end: int
    text: str


@dataclass(frozen=True)
class ParsedTable:
    """A parsed table: headers + ``header -> cell`` rows with a char span (§5.7).

    Fields
    ------
    headers
        Column headers in order (заголовки столбцов); de-duplicated so every
        row dict keeps one key per column.
    rows
        One ``dict`` per data row mapping each header to its cell string; every
        row has exactly ``n_cols`` keys (ragged rows padded with ``""``).
    span
        ``(start, end)`` char offsets of the table inside the source text
        (позиция таблицы в тексте). For a standalone parse it covers the parsed
        region; ``(-1, -1)`` when unknown.
    """

    headers: list[str]
    rows: list[dict[str, str]]
    span: tuple[int, int] = (-1, -1)

    @property
    def n_rows(self) -> int:
        """Number of data rows (число строк данных)."""
        return len(self.rows)

    @property
    def n_cols(self) -> int:
        """Number of columns (число столбцов) = number of headers."""
        return len(self.headers)

    def cell_at(self, row: int, col: int) -> str:
        """Cell value at ``(row, col)`` (0-based); raises ``IndexError`` if out of range."""
        if not (0 <= row < self.n_rows):
            raise IndexError(f"row {row} out of range (n_rows={self.n_rows})")
        if not (0 <= col < self.n_cols):
            raise IndexError(f"col {col} out of range (n_cols={self.n_cols})")
        return self.rows[row][self.headers[col]]

    def as_dict(self) -> dict[str, object]:
        """Full structured view (headers, rows, n_rows, n_cols, span)."""
        return {
            "headers": list(self.headers),
            "rows": [dict(r) for r in self.rows],
            "n_rows": self.n_rows,
            "n_cols": self.n_cols,
            "span": list(self.span),
        }


# --------------------------------------------------------------------------- #
# low-level line / cell helpers
# --------------------------------------------------------------------------- #
def _line_spans(text: str) -> list[_Line]:
    """Split *text* into lines carrying their absolute ``(start, end)`` char span."""
    out: list[_Line] = []
    start = 0
    for raw in text.splitlines(keepends=True):
        content = raw.rstrip("\n").rstrip("\r")
        out.append(_Line(start, start + len(content), content))
        start += len(raw)
    return out


def _split_pipe(line: str) -> list[str]:
    """Split a Markdown pipe row into stripped cells, dropping outer ``|`` bars."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_pipe_row(line: str) -> bool:
    return "|" in line and bool(line.strip())


def _is_separator(line: str) -> bool:
    """True for a Markdown header/body separator row (``--- | :-: | ---``)."""
    if "|" not in line and "-" not in line:
        return False
    cells = _split_pipe(line)
    return bool(cells) and all(bool(c) and _SEP_CELL_RE.fullmatch(c) for c in cells)


def _detect_delim(line: str) -> str | None:
    """Auto-detect a delimiter on *line*: tab, else multi-space, else ``None``."""
    if "\t" in line:
        return "\t"
    if _MULTISPACE_RE.search(line):
        return _MULTISPACE
    return None


def _split_delim(line: str, delim: str) -> list[str]:
    """Split *line* on *delim* (or the multi-space sentinel) into stripped cells."""
    if delim == _MULTISPACE:
        return [c.strip() for c in re.split(r"\s{2,}", line.strip())]
    return [c.strip() for c in line.split(delim)]


def _dedup_headers(headers: list[str]) -> list[str]:
    """Make header keys unique (a repeated header gets a ``_2`` / ``_3`` … suffix)."""
    counts: dict[str, int] = {}
    out: list[str] = []
    for h in headers:
        if h in counts:
            counts[h] += 1
            out.append(f"{h}_{counts[h]}")
        else:
            counts[h] = 1
            out.append(h)
    return out


def _build_table(
    headers: list[str],
    raw_rows: list[list[str]],
    span: tuple[int, int],
) -> ParsedTable:
    """Assemble a :class:`ParsedTable`, padding/truncating each row to ``n_cols``."""
    heads = _dedup_headers(headers)
    n_cols = len(heads)
    rows: list[dict[str, str]] = []
    for raw in raw_rows:
        cells = list(raw[:n_cols]) + [""] * (n_cols - len(raw))
        rows.append({heads[c]: cells[c] for c in range(n_cols)})
    return ParsedTable(headers=heads, rows=rows, span=span)


# --------------------------------------------------------------------------- #
# scanners — return (lines_consumed, ParsedTable | None) starting at index *i*
# --------------------------------------------------------------------------- #
def _scan_markdown(lines: list[_Line], i: int) -> tuple[int, ParsedTable | None]:
    """Try to read a Markdown pipe table starting at line *i*."""
    if i + 1 >= len(lines):
        return 0, None
    if not _is_pipe_row(lines[i].text) or not _is_separator(lines[i + 1].text):
        return 0, None
    headers = _split_pipe(lines[i].text)
    if not headers:
        return 0, None
    j = i + 2
    data_idx: list[int] = []
    while j < len(lines) and _is_pipe_row(lines[j].text) and not _is_separator(lines[j].text):
        data_idx.append(j)
        j += 1
    raw_rows = [_split_pipe(lines[k].text) for k in data_idx]
    last = data_idx[-1] if data_idx else i + 1
    span = (lines[i].start, lines[last].end)
    return j - i, _build_table(headers, raw_rows, span)


def _scan_delimited(
    lines: list[_Line],
    i: int,
    forced_sep: str | None,
) -> tuple[int, ParsedTable | None]:
    """Try to read a delimited table (TSV / multi-space / explicit sep) at line *i*."""
    first = lines[i].text
    if not first.strip():
        return 0, None
    delim = forced_sep if forced_sep is not None else _detect_delim(first)
    if delim is None:
        return 0, None
    if forced_sep is not None and forced_sep not in first:
        return 0, None
    header_cells = _split_delim(first, delim)
    if len(header_cells) < 2:  # a single column is prose, not a table
        return 0, None

    gathered = [i]
    j = i + 1
    while j < len(lines):
        t = lines[j].text
        if not t.strip():
            break
        if forced_sep is not None:
            if forced_sep not in t:
                break
        elif _detect_delim(t) != delim:
            break
        gathered.append(j)
        j += 1
    if len(gathered) < 2:  # need a header + at least one data row to be confident
        return 0, None

    raw_rows = [_split_delim(lines[k].text, delim) for k in gathered[1:]]
    span = (lines[gathered[0]].start, lines[gathered[-1]].end)
    return len(gathered), _build_table(header_cells, raw_rows, span)


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def parse_markdown_table(text: str) -> ParsedTable | None:
    """Parse the first Markdown pipe table in *text* (§5.7); ``None`` if none.

    A valid Markdown table needs a header row and a ``--- | ---`` separator row
    directly beneath it. Data rows may be ragged (padded) and cells may be empty
    (пустые ячейки → ``""``).
    """
    lines = _line_spans(text or "")
    for i in range(len(lines)):
        _, table = _scan_markdown(lines, i)
        if table is not None:
            return table
    return None


def parse_delimited(text: str, sep: str | None = None) -> ParsedTable | None:
    """Parse the first delimited table in *text* (§5.7); ``None`` if none.

    With *sep* ``None`` the delimiter is auto-detected — tab (TSV) first, then a
    multi-space *aligned* layout. Pass *sep* (``','`` / ``';'`` / ``'\\t'`` …) to
    force a specific single-character separator. The first row is the header;
    ragged rows are padded to ``n_cols``.
    """
    lines = _line_spans(text or "")
    for i in range(len(lines)):
        _, table = _scan_delimited(lines, i, sep)
        if table is not None:
            return table
    return None


def extract_tables(text: str) -> list[ParsedTable]:
    """Find every table in a block of mixed prose + tables (§5.7).

    Walks *text* line by line, preferring a Markdown pipe table at each position
    and otherwise an auto-detected delimited (TSV / multi-space) table. Prose
    lines are skipped, so a document with no tables yields ``[]``. Each returned
    :class:`ParsedTable` carries its character ``span`` in the source text.
    """
    lines = _line_spans(text or "")
    out: list[ParsedTable] = []
    i = 0
    n = len(lines)
    while i < n:
        consumed, table = _scan_markdown(lines, i)
        if table is not None:
            out.append(table)
            i += consumed
            continue
        consumed, table = _scan_delimited(lines, i, None)
        if table is not None:
            out.append(table)
            i += consumed
            continue
        i += 1
    return out

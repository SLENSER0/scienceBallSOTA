"""Table-cell Evidence resolver — клик по числу → точная ячейка таблицы (§6.10/§8.3).

Любое число, извлечённое из таблицы, несёт локатор ``table_id`` + ``row_index`` +
``col_index`` (§8.3). Этот модуль восстанавливает **исходную таблицу** и отмечает
ровно ту ячейку, из которой пришло число, — «максимальный уровень доверия»: куратор
видит число подсвеченным в реальной сетке PDF, а не просто ссылку на страницу.

Grid-источник выбирается по убыванию точности:

1. ``parsed`` — распарсенный sidecar загруженного документа
   (``runtime_dir/uploads/<doc>.json``, tables = ``[{page, rows}]``): полная сетка
   ячеек той страницы, где стоит evidence.
2. ``reconstructed`` — если sidecar-а нет (мигрированный корпус), сетка
   восстанавливается из «соседних» Evidence того же ``table_id`` (каждая несёт
   ``row_index``/``col_index``/``text``) — разреженная, но настоящая.
3. ``cell-only`` — крайний случай: 1×1 сетка из текста самой ячейки.

Публичный API:

* :func:`resolve_table_cell` — по ``evidence_id`` → payload с сеткой и подсветкой.
* :func:`resolve_locator`    — по явному локатору (§3.6) → тот же payload, для
  случая «кликнули по числу», когда материализованного Evidence-узла ещё нет.
* :class:`TableCellView`     — неизменяемый результат с :meth:`~TableCellView.as_dict`.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kg_common import get_settings
from kg_common.evidence_locator import (
    EvidenceLocator,
    from_evidence,
    validate_locator,
)

_TABLE_CELL = "table_cell"


@dataclass(frozen=True, slots=True)
class TableCellView:
    """Результат трассировки числа к ячейке исходной таблицы (§6.10/§8.3).

    ``grid`` — прямоугольная сетка строк-ячеек (строка 0 обычно заголовок);
    ``highlight`` = ``{"row", "col"}`` указывает подсвечиваемую ячейку (уже
    приведённую в границы сетки). ``source`` ∈ ``{parsed, reconstructed,
    cell-only}`` — насколько «настоящая» восстановленная таблица.
    """

    evidence_id: str | None
    is_table_cell: bool
    locator: EvidenceLocator
    locator_valid: bool
    grid: tuple[tuple[str, ...], ...]
    highlight_row: int
    highlight_col: int
    cell_text: str
    source: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready camelCase-совместимый payload для фронта (§17.13)."""
        return {
            "evidenceId": self.evidence_id,
            "isTableCell": self.is_table_cell,
            "docId": self.locator.doc_id or None,
            "page": self.locator.page,
            "tableId": self.locator.table_id,
            "rowIndex": self.locator.row_index,
            "colIndex": self.locator.col_index,
            "locator": self.locator.as_dict(),
            "locatorValid": self.locator_valid,
            "grid": [list(row) for row in self.grid],
            "nRows": len(self.grid),
            "nCols": max((len(r) for r in self.grid), default=0),
            "highlight": {"row": self.highlight_row, "col": self.highlight_col},
            "cellText": self.cell_text,
            "source": self.source,
            "detail": self.detail,
        }


# -- sidecar (uploaded documents) ---------------------------------------------


def _sidecar_path(doc_id: str) -> Path:
    """Path of the parsed sidecar for ``doc_id`` (mirrors documents router)."""
    safe = doc_id.replace(":", "_")
    return Path(get_settings().runtime_dir) / "uploads" / f"{safe}.json"


def _sidecar_tables(doc_id: str) -> list[dict[str, Any]]:
    """Parsed ``[{page, rows}]`` tables for ``doc_id`` — ``[]`` if no sidecar."""
    if not doc_id:
        return []
    p = _sidecar_path(doc_id)
    if not p.exists():
        return []
    with contextlib.suppress(json.JSONDecodeError, OSError, TypeError):
        data = json.loads(p.read_text(encoding="utf-8"))
        tables = data.get("tables")
        if isinstance(tables, list):
            return [t for t in tables if isinstance(t, dict)]
    return []


def _norm_grid(rows: Any) -> tuple[tuple[str, ...], ...]:
    """Coerce raw ``rows`` into a tuple-of-tuples of strings."""
    grid: list[tuple[str, ...]] = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, list):
                grid.append(tuple("" if c is None else str(c) for c in row))
    return tuple(grid)


def _cell(grid: tuple[tuple[str, ...], ...], row: int, col: int) -> str | None:
    """Cell text at ``(row, col)`` or ``None`` if out of bounds."""
    if 0 <= row < len(grid) and 0 <= col < len(grid[row]):
        return grid[row][col]
    return None


def _pick_parsed_grid(
    tables: list[dict[str, Any]],
    loc: EvidenceLocator,
    cell_text: str,
) -> tuple[tuple[str, ...], ...] | None:
    """Choose the parsed table the evidence points at — pick the best of a page.

    Candidates are the tables on ``loc.page`` (all tables if the page is unknown).
    A table is preferred when its cell at ``(row_index, col_index)`` reproduces the
    evidence text; otherwise the first candidate whose bounds contain the cell; then
    simply the first candidate. Returns ``None`` when there are no candidates.
    """
    cands = [t for t in tables if loc.page is None or t.get("page") == loc.page]
    if not cands and loc.page is not None:
        cands = tables  # page mismatch — fall back to any parsed table
    if not cands:
        return None

    row = loc.row_index if loc.row_index is not None else -1
    col = loc.col_index if loc.col_index is not None else -1
    want = (cell_text or "").strip()

    text_match: tuple[tuple[str, ...], ...] | None = None
    in_bounds: tuple[tuple[str, ...], ...] | None = None
    for t in cands:
        grid = _norm_grid(t.get("rows"))
        if not grid:
            continue
        got = _cell(grid, row, col)
        if got is not None:
            if in_bounds is None:
                in_bounds = grid
            if want and got.strip() == want:
                text_match = grid
                break
    if text_match is not None:
        return text_match
    if in_bounds is not None:
        return in_bounds
    first = _norm_grid(cands[0].get("rows"))
    return first or None


# -- sibling reconstruction (migrated corpus) ---------------------------------

_SIBLING_CYPHER = (
    "MATCH (e:Node {label:'Evidence'}) WHERE e.table_id=$tid "
    "RETURN e.row_index, e.col_index, e.text LIMIT 500"
)


def _reconstruct_grid(store: Any, table_id: str) -> tuple[tuple[str, ...], ...]:
    """Rebuild a sparse grid from every Evidence sharing ``table_id`` (§8.3).

    Robust across backends: the Cypher is wrapped because an embedded Kuzu store
    without a ``table_id`` column raises a binder error rather than returning rows.
    """
    cells: list[tuple[int, int, str]] = []
    with contextlib.suppress(Exception):
        for r in store.rows(_SIBLING_CYPHER, {"tid": table_id}):
            if r[0] is None or r[1] is None:
                continue
            cells.append((int(r[0]), int(r[1]), "" if r[2] is None else str(r[2])))
    if not cells:
        return ()
    n_rows = max(c[0] for c in cells) + 1
    n_cols = max(c[1] for c in cells) + 1
    grid = [["" for _ in range(n_cols)] for _ in range(n_rows)]
    for row, col, text in cells:
        grid[row][col] = text
    return tuple(tuple(r) for r in grid)


# -- assembly -----------------------------------------------------------------


def _clamp(value: int | None, hi: int) -> int:
    """Clamp ``value`` into ``[0, hi]`` (0 when unset / grid empty)."""
    if value is None or hi < 0:
        return 0
    return max(0, min(value, hi))


def _assemble(
    store: Any,
    *,
    evidence_id: str | None,
    loc: EvidenceLocator,
    cell_text: str,
) -> TableCellView:
    """Resolve a locator to a grid + highlighted cell, choosing the best source."""
    valid, _errs = validate_locator(loc)

    grid = _pick_parsed_grid(_sidecar_tables(loc.doc_id), loc, cell_text)
    source = "parsed"
    detail = "исходная таблица восстановлена из распарсенного документа"

    if grid is None and loc.table_id:
        grid = _reconstruct_grid(store, loc.table_id) or None
        if grid is not None:
            source = "reconstructed"
            detail = "таблица восстановлена из соседних Evidence того же table_id"

    r = loc.row_index if loc.row_index is not None else 0
    c = loc.col_index if loc.col_index is not None else 0
    if grid is None:
        # Cell-only: no grid available — surface the single cell so the click still
        # traces to a concrete value rather than dead-ending.
        grid = ((cell_text or "",),)
        source = "cell-only"
        detail = "полная таблица недоступна — показана только исходная ячейка"
        r = c = 0

    hi_row = len(grid) - 1
    hrow = _clamp(r, hi_row)
    hi_col = (len(grid[hrow]) - 1) if grid else -1
    hcol = _clamp(c, hi_col)
    resolved_text = _cell(grid, hrow, hcol) or cell_text

    return TableCellView(
        evidence_id=evidence_id,
        is_table_cell=True,
        locator=loc,
        locator_valid=valid,
        grid=grid,
        highlight_row=hrow,
        highlight_col=hcol,
        cell_text=resolved_text,
        source=source,
        detail=detail,
    )


def resolve_table_cell(store: Any, evidence_id: str) -> TableCellView | None:
    """Trace a table-cell Evidence node to its source table + highlighted cell.

    Returns ``None`` when ``evidence_id`` is unknown. When the evidence is not a
    table cell (a paragraph / caption span) the returned view has
    ``is_table_cell=False`` and an empty grid — the caller renders «не табличное».
    """
    nd = store.get_node(evidence_id)
    if nd is None:
        return None
    loc = from_evidence(nd)
    cell_text = str(nd.get("text") or "")
    if loc.source_type != _TABLE_CELL and loc.table_id is None:
        return TableCellView(
            evidence_id=evidence_id,
            is_table_cell=False,
            locator=loc,
            locator_valid=validate_locator(loc)[0],
            grid=(),
            highlight_row=-1,
            highlight_col=-1,
            cell_text=cell_text,
            source="none",
            detail="это доказательство не является ячейкой таблицы",
        )
    return _assemble(store, evidence_id=evidence_id, loc=loc, cell_text=cell_text)


def resolve_locator(store: Any, ev: dict[str, Any]) -> TableCellView:
    """Resolve an explicit locator mapping (§3.6) — the «клик по числу» path.

    Used when a number carries its own ``table_id``/``row_index``/``col_index``
    (and ``doc_id``/``page``/``text``) without a materialised Evidence node yet.
    """
    loc = from_evidence(ev)
    return _assemble(
        store,
        evidence_id=str(ev.get("evidence_id") or ev.get("id") or "") or None,
        loc=loc,
        cell_text=str(ev.get("text") or ""),
    )

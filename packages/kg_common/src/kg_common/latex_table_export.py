"""Comparison/metrics table export to LaTeX ``booktabs`` (§22).

Рендер таблицы сравнения/метрик (comparison/metrics table) в LaTeX
``tabular`` окружение с ``booktabs`` линейками (``\\toprule`` /
``\\midrule`` / ``\\bottomrule``) для готовых к публикации отчётов —
paper-ready reports.

The sibling :mod:`kg_common.tabular_export` covers only CSV / Markdown /
XLSX; this module adds the LaTeX target so metrics tables can be dropped
straight into a paper.

Cell rendering mirrors :mod:`kg_common.tabular_export`: a column missing from
a row (or present as ``None``) renders as an empty cell (``""``); any other
value is stringified with :func:`str`. LaTeX-significant characters
(``& % _ # $``) are escaped so the output compiles — экранирование
спецсимволов LaTeX.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# LaTeX-significant characters escaped in cell text. ``\\`` is *not* in the set,
# so each single-pass replacement is independent (no double-escaping) — §22.
_LATEX_ESCAPE: tuple[tuple[str, str], ...] = (
    ("&", r"\&"),
    ("%", r"\%"),
    ("_", r"\_"),
    ("#", r"\#"),
    ("$", r"\$"),
)


def _cell(value: Any) -> str:
    """Render one cell value; ``None`` (incl. missing keys) -> empty string."""
    return "" if value is None else str(value)


def _escape(text: str) -> str:
    """Escape LaTeX-significant characters ``& % _ # $`` — экранирование."""
    for raw, repl in _LATEX_ESCAPE:
        text = text.replace(raw, repl)
    return text


@dataclass(frozen=True)
class LatexTable:
    """A LaTeX ``tabular`` model — модель таблицы LaTeX (§22).

    Attributes
    ----------
    columns:
        Header labels, left-to-right — заголовки столбцов.
    rows:
        Data rows, each a tuple of already-stringified (unescaped) cells.
    col_spec:
        The column specification string for ``\\begin{tabular}{...}`` (e.g.
        ``"lr"``) — one alignment char per column.
    """

    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    col_spec: str

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-``dict`` view — сериализуемое представление."""
        return {
            "columns": list(self.columns),
            "rows": [list(row) for row in self.rows],
            "col_spec": self.col_spec,
        }


def build_table(
    rows: list[dict[str, Any]],
    columns: list[str],
    *,
    aligns: dict[str, str] | None = None,
) -> LatexTable:
    """Build a :class:`LatexTable` from ``rows`` — построение таблицы (§22).

    Each column maps to one ``col_spec`` character: ``aligns[col]`` if given,
    else ``'l'`` (left). Cells are stringified with :func:`str`; a column
    missing from a row (or ``None``) becomes an empty cell. Escaping is
    deferred to :func:`to_latex`, so :class:`LatexTable` holds raw text.
    """
    aligns = aligns or {}
    col_spec = "".join(aligns.get(col, "l") for col in columns)
    data = tuple(tuple(_cell(row.get(col)) for col in columns) for row in rows)
    return LatexTable(columns=tuple(columns), rows=data, col_spec=col_spec)


def _render_row(cells: tuple[str, ...]) -> str:
    """Render one LaTeX row: ``a & b \\\\`` with escaped cells — строка."""
    return " & ".join(_escape(cell) for cell in cells) + r" \\"


def to_latex(t: LatexTable, *, caption: str | None = None, label: str | None = None) -> str:
    """Render ``t`` to a LaTeX ``booktabs`` string — рендер в LaTeX (§22).

    The core is always a ``tabular`` environment::

        \\begin{tabular}{ll}
        \\toprule
        A & B \\\\
        \\midrule
        ... data rows ...
        \\bottomrule
        \\end{tabular}

    When ``caption`` and/or ``label`` is given the ``tabular`` is wrapped in a
    floating ``table`` environment carrying ``\\caption{...}`` /
    ``\\label{...}``; otherwise the output starts directly with
    ``\\begin{tabular}``. Header labels and cells are LaTeX-escaped.
    """
    lines: list[str] = [
        r"\begin{tabular}{" + t.col_spec + "}",
        r"\toprule",
        _render_row(t.columns),
        r"\midrule",
    ]
    lines.extend(_render_row(row) for row in t.rows)
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")

    if caption is None and label is None:
        return "\n".join(lines)

    wrapped: list[str] = [r"\begin{table}", r"\centering"]
    wrapped.extend(lines)
    if caption is not None:
        wrapped.append(r"\caption{" + _escape(caption) + "}")
    if label is not None:
        # A \label is a cross-reference key, not display text — не экранируем.
        wrapped.append(r"\label{" + label + "}")
    wrapped.append(r"\end{table}")
    return "\n".join(wrapped)

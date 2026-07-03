"""Side-by-side comparison of technology solutions by measured property (§24.24).

Сравнение технологических решений (*technology solutions*) — берёт список решений
и выстраивает их бок о бок как колонки таблицы, где строки — это измеряемые свойства
(*measured properties*), а ячейка несёт лучшее измеренное значение свойства для решения.
Отсутствующее значение отображается пустым (*blank*).

English: :func:`compare_solutions` takes a list of solution node ids and lines them up as
table columns (``solutions``). The rows are the union of measured property names seen across
those solutions (``rows``); each cell holds the peak measured ``value_normalized`` for that
``(property, solution)`` pair. A solution that never measured a given property leaves that
cell empty — rendered as a blank string in :meth:`ComparisonTable.as_dict`.

Scoping: an optional ``property`` keyword narrows the rows to that single property (an empty
table if no compared solution measured it). Ids that do not resolve to a node are dropped
(order-preserving, de-duplicated); an empty / all-unknown id list yields an empty table.

Kuzu note (§3 / ADR-0005): custom node props are **not** queryable columns, so the neighbour
walk RETURNs only the base ``id`` column and the measured ``property_name`` / ``value_normalized``
/ ``normalized_unit`` are read through :meth:`KuzuGraphStore.get_node` (which merges base
columns with the ``props`` JSON). The module is read-only: it never writes to the graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_retrievers.graph_store import KuzuGraphStore

# Base node columns a measurement carries (all queryable, read via ``get_node``) (§24.24).
PROPERTY_COLUMN = "property_name"
VALUE_COLUMN = "value_normalized"
UNIT_COLUMN = "normalized_unit"

# Rendering of a missing ``(property, solution)`` cell in ``as_dict`` (§24.24).
BLANK = ""


@dataclass(frozen=True)
class Cell:
    """One ``(property, solution)`` intersection of the comparison table (§24.24).

    Carries the peak measured ``value`` for ``solution``'s ``property``, its ``unit`` and the
    ``measurement_id`` the value was read from. A missing intersection has no ``Cell`` at all
    (it renders blank in :meth:`ComparisonTable.as_dict`).
    """

    solution: str
    property: str
    value: float | None
    unit: str | None
    measurement_id: str | None

    def as_dict(self) -> dict[str, Any]:
        """JSON cell shape ``{solution, property, value, unit, measurement_id}``."""
        return {
            "solution": self.solution,
            "property": self.property,
            "value": self.value,
            "unit": self.unit,
            "measurement_id": self.measurement_id,
        }


@dataclass(frozen=True)
class ComparisonTable:
    """A property × solution comparison table over a graph (§24.24).

    ``solutions`` are the compared solution ids (columns, input order preserved), ``rows`` the
    measured property names (sorted), and ``cells`` a sparse ``property -> solution -> Cell``
    map (a solution with no value for a property simply contributes no cell there).
    """

    solutions: tuple[str, ...]
    rows: tuple[str, ...]
    cells: dict[str, dict[str, Cell]]

    @property
    def is_empty(self) -> bool:
        """True when no compared solution measured any (in-scope) property."""
        return not self.rows

    def cell(self, prop: str, solution: str) -> Cell | None:
        """The cell at ``(prop, solution)`` or ``None`` if the intersection is empty."""
        return self.cells.get(prop, {}).get(solution)

    def value(self, prop: str, solution: str) -> float | None:
        """Peak measured value at ``(prop, solution)`` (``None`` if the cell is empty)."""
        found = self.cell(prop, solution)
        return found.value if found is not None else None

    def as_dict(self) -> dict[str, Any]:
        """JSON table shape ``{solutions, rows, cells}`` (§24.24).

        ``cells`` is a dense ``{property: {solution: cell_or_blank}}`` grid: every compared
        solution appears under every row, with a missing value rendered as ``""`` (blank).
        """
        return {
            "solutions": list(self.solutions),
            "rows": list(self.rows),
            "cells": {
                prop: {
                    sol: (found.as_dict() if (found := self.cell(prop, sol)) is not None else BLANK)
                    for sol in self.solutions
                }
                for prop in self.rows
            },
        }


def _existing_solutions(store: KuzuGraphStore, ids: list[str]) -> list[str]:
    """Input ids that resolve to a node — order-preserving and de-duplicated (§24.24)."""
    seen: set[str] = set()
    out: list[str] = []
    for sid in ids:
        if sid in seen:
            continue
        seen.add(sid)
        if store.get_node(sid) is not None:
            out.append(sid)
    return out


def _as_value(raw: object) -> float | None:
    """Coerce a raw ``value_normalized`` cell to ``float`` (``None`` when absent / non-numeric)."""
    if isinstance(raw, bool):  # bool is an int subclass — never a measured value
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


def _measurements(
    store: KuzuGraphStore, solution_id: str
) -> dict[str, tuple[float, str | None, str]]:
    """Measured nodes linked to a solution as ``property_name -> (value, unit, measurement_id)``.

    Walks edges in either direction and keeps only neighbours carrying a numeric
    ``value_normalized`` and a ``property_name``. The **peak** value wins per property; visiting
    measurements in ascending id order breaks ties toward the lowest-id measurement. Custom
    props are read via ``get_node`` (Kuzu: only base columns are queryable).
    """
    rows = store.rows(
        "MATCH (s:Node {id:$sid})-[r:Rel]-(m:Node) "
        "WHERE m.value_normalized IS NOT NULL AND m.id <> $sid "
        "RETURN DISTINCT m.id ORDER BY m.id",
        {"sid": solution_id},
    )
    best: dict[str, tuple[float, str | None, str]] = {}
    for (mid,) in rows:
        node = store.get_node(mid)
        if not node:
            continue
        raw_prop = node.get(PROPERTY_COLUMN)
        value = _as_value(node.get(VALUE_COLUMN))
        if raw_prop is None or value is None:
            continue
        prop = str(raw_prop)
        raw_unit = node.get(UNIT_COLUMN)
        unit = raw_unit if isinstance(raw_unit, str) else None
        current = best.get(prop)
        if current is None or value > current[0]:
            best[prop] = (value, unit, mid)
    return best


def compare_solutions(
    store: KuzuGraphStore, ids: list[str], *, property: str | None = None
) -> ComparisonTable:
    """Compare ``ids`` solutions side by side by their measured property values (§24.24).

    Each compared solution becomes a column (``solutions``, input order preserved, unknown ids
    dropped); the rows are the union of measured ``property_name`` values across them (sorted),
    optionally narrowed to a single ``property``. Each cell holds the peak measured value for
    that ``(property, solution)`` pair; a solution that never measured a property leaves the
    cell empty (blank in :meth:`ComparisonTable.as_dict`). An empty / all-unknown id list — or a
    ``property`` no compared solution measured — yields an empty table (graceful, no error).
    """
    solutions = _existing_solutions(store, ids)
    per_solution = {sid: _measurements(store, sid) for sid in solutions}

    props: set[str] = set()
    for measured in per_solution.values():
        props.update(measured)
    if property is not None:
        props &= {property}
    rows = tuple(sorted(props))

    cells: dict[str, dict[str, Cell]] = {}
    for prop in rows:
        row_cells: dict[str, Cell] = {}
        for sid in solutions:
            found = per_solution[sid].get(prop)
            if found is None:
                continue
            value, unit, mid = found
            row_cells[sid] = Cell(
                solution=sid, property=prop, value=value, unit=unit, measurement_id=mid
            )
        if row_cells:
            cells[prop] = row_cells

    return ComparisonTable(solutions=tuple(solutions), rows=rows, cells=cells)

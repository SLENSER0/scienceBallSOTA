"""Domain-specific comparison matrices (§24.11).

Матрицы сравнения технологических решений — turns a slice of the knowledge graph
into a *method × component* table so an analyst can line up competing
``TechnologySolution`` methods (rows) against the target components / indicators
they act on (columns) and read the best measured value in each intersecting cell.

The audit (§24.11) found only one generic table; this module adds the domain-aware
matrices. Two builders share one engine:

- :func:`build_method_component_matrix` — the water-treatment (обессоливание) style
  matrix: ``TechnologySolution`` methods × their measured indicators, each cell
  carrying the best (peak) measured value **and** the method's applicability
  condition (условие применимости);
- :func:`build_comparison` — a generic matrix over any ``row_label`` node type and
  any node ``col_property`` (base column *or* custom prop) that seeds the columns.

Kuzu note (§3 / ADR-0005): custom node props are **not** queryable columns, so the
column key and measured value for each linked node are read through
:meth:`KuzuGraphStore.get_node` (which merges base columns + the ``props`` JSON),
never via a bare ``RETURN n.<custom_prop>``. Only base columns / rel columns are
RETURNed directly.

The module is read-only: it never writes to the graph. Results are frozen
dataclasses exposing ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from kg_retrievers.graph_store import NODE_COLUMNS, KuzuGraphStore

# Node label whose instances are the *methods* compared as rows (§24.11).
SOLUTION_LABEL = "TechnologySolution"

# Default node property whose values seed the *component / indicator* columns.
COMPONENT_PROPERTY = "property_name"

# Relation linking a method to an applicability condition (условие применимости).
APPLICABILITY_REL = "HAS_APPLICABILITY_CONDITION"

# Default domain for the method-component matrix (обессоливание шахтных вод).
DEFAULT_DOMAIN = "water_treatment"

# Base (queryable) node columns — everything else lives in the ``props`` JSON and
# must be read via ``get_node`` (Kuzu constraint, see module docstring).
_BASE_NODE_COLS: frozenset[str] = frozenset(c for c, _ in NODE_COLUMNS)


@dataclass(frozen=True)
class MatrixCell:
    """One method × component intersection (§24.11).

    Holds the *best* (peak) measured value linking a ``row`` method to a ``column``
    component/indicator, its unit, the method's ``applicability`` note (условие
    применимости, when present), the source measurement id and any linked Evidence.
    """

    row: str  # method / row-node id
    column: str  # component / indicator key
    value: float | None  # best (peak) measured value
    unit: str | None
    applicability: str | None  # method-level applicability condition text, or None
    measurement_id: str | None  # node the best value was read from
    evidence_ids: tuple[str, ...]  # linked Evidence ids (edges + SUPPORTED_BY), sorted

    def as_dict(self) -> dict:
        """JSON cell shape (§24.11)."""
        return {
            "row": self.row,
            "column": self.column,
            "value": self.value,
            "unit": self.unit,
            "applicability": self.applicability,
            "measurement_id": self.measurement_id,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class ComparisonMatrix:
    """A method × component comparison table over a graph (§24.11).

    ``rows`` are the compared node ids (methods), ``columns`` the component /
    indicator keys, and ``cells`` a sparse ``row_id -> col_key -> MatrixCell`` map
    (a method with no measured indicator simply contributes no cells).
    """

    domain: str | None
    row_label: str
    col_property: str
    rows: tuple[str, ...]
    columns: tuple[str, ...]
    cells: dict[str, dict[str, MatrixCell]]

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    @property
    def n_columns(self) -> int:
        return len(self.columns)

    @property
    def is_empty(self) -> bool:
        return not self.rows

    def cell(self, row: str, column: str) -> MatrixCell | None:
        """The cell at ``(row, column)`` or ``None`` if the intersection is empty."""
        return self.cells.get(row, {}).get(column)

    def value(self, row: str, column: str) -> float | None:
        """Best measured value at ``(row, column)`` (``None`` if the cell is empty)."""
        found = self.cell(row, column)
        return found.value if found is not None else None

    def as_dict(self) -> dict:
        """JSON table shape ``{rows, columns, cells}`` (§24.11).

        ``cells`` is a nested, deterministically ordered ``{row: {col: cell}}`` map.
        """
        return {
            "rows": list(self.rows),
            "columns": list(self.columns),
            "cells": {
                r: {c: cell.as_dict() for c, cell in sorted(cols.items())}
                for r, cols in sorted(self.cells.items())
            },
        }


def _parse_evidence(raw: object) -> list[str]:
    """Parse an edge ``evidence_ids`` JSON string into a list (empty on failure)."""
    if not isinstance(raw, str) or not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(x) for x in parsed] if isinstance(parsed, list) else []


def _row_ids(store: KuzuGraphStore, label: str, domain: str | None) -> list[str]:
    """All in-scope ``label`` node ids, optionally scoped by ``domain`` (sorted)."""
    cypher = "MATCH (s:Node) WHERE s.label=$label "
    params: dict[str, object] = {"label": label}
    if domain is not None:
        cypher += "AND s.domain=$domain "
        params["domain"] = domain
    cypher += "RETURN s.id ORDER BY s.id"
    return [r[0] for r in store.rows(cypher, params)]


def _linked_measurements(store: KuzuGraphStore, row_id: str) -> dict[str, set[str]]:
    """Measurement/indicator nodes directly linked to ``row_id`` → their edge evidence.

    Walks edges in either direction (measurement→method via ``ABOUT_REGIME`` or
    method→indicator via ``HAS_TECHNOECONOMIC_INDICATOR``) and keeps only neighbours
    that actually carry a measured ``value_normalized``. Only base/rel columns are
    RETURNed here; per-node props are read later via ``get_node``.
    """
    rows = store.rows(
        "MATCH (s:Node {id:$sid})-[r:Rel]-(m:Node) "
        "WHERE m.value_normalized IS NOT NULL AND m.id <> $sid "
        "RETURN DISTINCT m.id, r.evidence_ids ORDER BY m.id",
        {"sid": row_id},
    )
    out: dict[str, set[str]] = {}
    for mid, edge_eids in rows:
        out.setdefault(mid, set()).update(_parse_evidence(edge_eids))
    return out


def _supported_evidence(store: KuzuGraphStore, measurement_id: str) -> list[str]:
    """Evidence node ids the measurement is ``SUPPORTED_BY`` (Evidence only)."""
    rows = store.rows(
        "MATCH (m:Node {id:$mid})-[r:Rel]->(e:Node) "
        "WHERE r.type='SUPPORTED_BY' AND e.label='Evidence' "
        "RETURN DISTINCT e.id ORDER BY e.id",
        {"mid": measurement_id},
    )
    return [r[0] for r in rows]


def _applicability(store: KuzuGraphStore, row_id: str) -> str | None:
    """The method's applicability condition text (условие применимости), if any.

    Reads each ``HAS_APPLICABILITY_CONDITION`` target through ``get_node`` (so a
    custom-prop-only condition still resolves) and joins their names deterministically.
    """
    rows = store.rows(
        "MATCH (s:Node {id:$sid})-[r:Rel]->(ac:Node) WHERE r.type=$rel "
        "RETURN DISTINCT ac.id ORDER BY ac.id",
        {"sid": row_id, "rel": APPLICABILITY_REL},
    )
    names: list[str] = []
    for row in rows:
        acid = row[0]
        node = store.get_node(acid)
        if not node:
            continue
        name = node.get("name") or node.get("canonical_name") or node.get("text") or acid
        names.append(str(name))
    if not names:
        return None
    return " | ".join(sorted(names))


def _is_better(new_value: float | None, cur_value: float | None) -> bool:
    """True if ``new_value`` is a strictly better (higher/peak) measured value.

    Nodes are visited in ascending id order, so an equal value keeps the first
    (lowest-id) measurement — deterministic tie-breaking without extra state.
    """
    if new_value is None:
        return False
    if cur_value is None:
        return True
    return new_value > cur_value


def _build(
    store: KuzuGraphStore,
    *,
    row_label: str,
    col_property: str,
    domain: str | None,
    with_applicability: bool,
) -> ComparisonMatrix:
    """Shared engine for both matrix builders (§24.11)."""
    row_ids = _row_ids(store, row_label, domain)
    cells: dict[str, dict[str, MatrixCell]] = {}
    columns: set[str] = set()

    for rid in row_ids:
        applicability = _applicability(store, rid) if with_applicability else None
        linked = _linked_measurements(store, rid)
        # col_key -> (value, unit, measurement_id, evidence)
        best: dict[str, tuple[float | None, str | None, str, tuple[str, ...]]] = {}
        for mid in sorted(linked):
            node = store.get_node(mid)  # base cols + props (Kuzu: custom props via get_node)
            if not node:
                continue
            raw_key = node.get(col_property)
            if raw_key is None:
                continue
            col_key = str(raw_key)
            raw_val = node.get("value_normalized")
            value = float(raw_val) if isinstance(raw_val, (int, float)) else None
            raw_unit = node.get("normalized_unit")
            unit = raw_unit if isinstance(raw_unit, str) else None
            current = best.get(col_key)
            if current is None or _is_better(value, current[0]):
                evidence = tuple(sorted(linked[mid] | set(_supported_evidence(store, mid))))
                best[col_key] = (value, unit, mid, evidence)

        if not best:
            continue
        row_cells: dict[str, MatrixCell] = {}
        for col_key, (value, unit, mid, evidence) in best.items():
            columns.add(col_key)
            row_cells[col_key] = MatrixCell(
                row=rid,
                column=col_key,
                value=value,
                unit=unit,
                applicability=applicability,
                measurement_id=mid,
                evidence_ids=evidence,
            )
        cells[rid] = row_cells

    return ComparisonMatrix(
        domain=domain,
        row_label=row_label,
        col_property=col_property,
        rows=tuple(row_ids),
        columns=tuple(sorted(columns)),
        cells=cells,
    )


def build_method_component_matrix(
    store: KuzuGraphStore, *, domain: str = DEFAULT_DOMAIN
) -> ComparisonMatrix:
    """Build a method × component matrix for ``domain`` (§24.11).

    Rows are the in-domain ``TechnologySolution`` methods; columns are the
    ``property_name`` indicators / components measured for them; each cell carries
    the best (peak) measured value plus the method's applicability condition. An
    empty or ``domain``-absent graph yields an empty matrix (graceful, no error).
    """
    return _build(
        store,
        row_label=SOLUTION_LABEL,
        col_property=COMPONENT_PROPERTY,
        domain=domain,
        with_applicability=True,
    )


def build_comparison(
    store: KuzuGraphStore,
    *,
    row_label: str,
    col_property: str,
    domain: str | None = None,
) -> ComparisonMatrix:
    """Build a generic comparison matrix over any node type / property (§24.11).

    Rows are the in-scope ``row_label`` nodes; columns are the distinct values of
    ``col_property`` (a base column *or* a custom prop, both read via ``get_node``)
    over the measured nodes linked to each row; each cell holds the best measured
    value. Applicability is not resolved here (that is method-specific — see
    :func:`build_method_component_matrix`).
    """
    return _build(
        store,
        row_label=row_label,
        col_property=col_property,
        domain=domain,
        with_applicability=False,
    )

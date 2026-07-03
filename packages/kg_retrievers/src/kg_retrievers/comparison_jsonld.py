"""§24.13/§24.16 — export a technology-comparison table to JSON-LD.

Экспорт сравнительной таблицы в JSON-LD (export of the comparison table to
JSON-LD). The §24.13/§24.16 audit found the piece missing: ``report_builder``
emits Markdown only, and ``graph_jsonld_serializer`` serializes the *graph*, not
a comparison *table*. This module fills that gap with a tiny, pure serializer.

A comparison table is three plain inputs the caller already holds:

- ``rows`` — the compared alternatives (row labels), one JSON-LD node each;
- ``cols`` — the comparison criteria (column keys), one property per node;
- ``cells`` — a sparse ``(row, col) -> payload`` map. A payload either measures
  the intersection (``value`` / ``unit`` / ``evidence_ids``) or marks it a *gap*
  (``{"gap": True}``). Any ``(row, col)`` absent from ``cells`` is itself a gap.

The output is a JSON-LD document ``{"@context": {...}, "@graph": [...]}``: the
``@context`` maps every criterion key to a domain IRI (derived from
``context_iri``), and ``@graph`` carries one node per row. Each node has a
deterministic ``@id`` (slugged from its row label) and, for every column, either
a measured property object ``{"value", "unit", "evidence_ids"}`` or a gap marker
``{"gap": True}`` with **no** value.

Stdlib ``json`` only — no graph store, no I/O — so there is no Kuzu column
caveat here: every field is read straight off the dicts the caller hands us.
:func:`comparison_to_jsonld` returns the plain dict; :class:`ComparisonJsonLd`
is the frozen intermediate exposing :meth:`~ComparisonJsonLd.as_dict`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Default domain @context base IRI (RU: базовый IRI доменного контекста).
DEFAULT_CONTEXT_IRI = "https://scienceball/domain#"

# Row-label characters kept in a slug; every run of the rest collapses to "-".
_SLUG_STRIP = re.compile(r"[^0-9a-z]+")


def _slug(label: str) -> str:
    """Deterministic URL-safe slug for a row label (RU: детерминированный slug).

    Lower-cases, replaces every run of non-alphanumerics with a single ``-`` and
    trims leading/trailing ``-``. An empty/punctuation-only label yields ``item``
    so the ``@id`` is always non-empty. The mapping is pure, so equal labels
    always produce the same slug (§24.13 assertion 5).
    """
    slug = _SLUG_STRIP.sub("-", label.strip().lower()).strip("-")
    return slug or "item"


def _row_iri(context_iri: str, label: str) -> str:
    """Deterministic ``@id`` IRI for a row label (RU: идентификатор строки-узла)."""
    return f"{context_iri}{_slug(label)}"


def _is_gap(cell: dict[str, Any] | None) -> bool:
    """True when a ``(row, col)`` cell is a gap: absent or explicitly flagged."""
    return cell is None or bool(cell.get("gap"))


def _cell_property(cell: dict[str, Any]) -> dict[str, Any]:
    """Serialize a measured cell payload into a JSON-LD property object.

    Copies ``value`` and ``unit`` through when present and always carries an
    ``evidence_ids`` **list** (a fresh copy, empty when the payload had none), so
    a cell with evidence keeps its ids (§24.13 assertion 3).
    """
    prop: dict[str, Any] = {}
    if "value" in cell:
        prop["value"] = cell["value"]
    if "unit" in cell:
        prop["unit"] = cell["unit"]
    prop["evidence_ids"] = list(cell.get("evidence_ids", ()))
    return prop


@dataclass(frozen=True)
class ComparisonJsonLd:
    """§24.13 — a JSON-LD comparison document: its ``@context`` and ``@graph``.

    ``context`` maps every criterion key to its domain IRI; ``graph`` is the
    ordered tuple of row nodes. RU: контекст критериев и узлы-альтернативы.
    """

    context: dict[str, Any]
    graph: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        """Return the JSON-LD document as a plain dict (RU: словарь-документ)."""
        return {"@context": self.context, "@graph": [dict(n) for n in self.graph]}


def build_comparison_jsonld(
    rows: list[str],
    cols: list[str],
    cells: dict[tuple[str, str], dict[str, Any]],
    *,
    context_iri: str = DEFAULT_CONTEXT_IRI,
) -> ComparisonJsonLd:
    """Assemble a comparison table into a frozen :class:`ComparisonJsonLd` (§24.13).

    Builds the criterion ``@context`` (``col -> context_iri + col``) and one node
    per row. Each node gets a deterministic ``@id`` and, for every column, either
    the measured property (:func:`_cell_property`) or a ``{"gap": True}`` marker
    when the ``(row, col)`` is absent from ``cells`` or explicitly flagged a gap.
    """
    context: dict[str, Any] = {col: f"{context_iri}{col}" for col in cols}
    graph: list[dict[str, Any]] = []
    for row in rows:
        node: dict[str, Any] = {"@id": _row_iri(context_iri, row)}
        for col in cols:
            cell = cells.get((row, col))
            node[col] = {"gap": True} if _is_gap(cell) else _cell_property(cell)
        graph.append(node)
    return ComparisonJsonLd(context=context, graph=tuple(graph))


def comparison_to_jsonld(
    rows: list[str],
    cols: list[str],
    cells: dict[tuple[str, str], dict[str, Any]],
    *,
    context_iri: str = DEFAULT_CONTEXT_IRI,
) -> dict[str, Any]:
    """Serialize a comparison table to a JSON-LD dict (§24.13/§24.16).

    Convenience wrapper over :func:`build_comparison_jsonld` returning the plain
    ``{"@context": {...}, "@graph": [...]}`` document (``len(@graph) == len(rows)``).
    The result contains only JSON-native types, so ``json.dumps`` round-trips it
    without error. RU: экспорт сравнительной таблицы в JSON-LD.
    """
    return build_comparison_jsonld(rows, cols, cells, context_iri=context_iri).as_dict()

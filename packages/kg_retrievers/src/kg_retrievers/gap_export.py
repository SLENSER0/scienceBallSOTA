"""Gap export to CSV / JSON (§15.13).

The gap scanner (:mod:`kg_retrievers.gap_analysis`, §15) materializes many
``Gap`` nodes and §15.9 (:mod:`kg_retrievers.gap_scoring`) scores and explains
each one. §15.13 makes those gaps *portable*: it flattens a list of gap dicts
into export-ready rows — each carrying the computed priority ``score`` plus the
normalized ``gap_type`` and ``domain`` — then serializes them to CSV or JSON so
a curator can open them in a spreadsheet (таблица) or feed them to another tool.

Three entry points, all pure python (stdlib :mod:`csv` / :mod:`json`, no graph
or store access — callers assemble the gap dicts, e.g. via
:func:`kg_retrievers.gap_dashboard.build_gap_dashboard`):

- :func:`gap_export_rows` — flatten gaps to row dicts (score + type + domain);
- :func:`gaps_to_csv` — a CSV document (header + one line per gap), RU-safe;
- :func:`gaps_to_json` — a JSON array of the same rows, RU preserved verbatim.

The ``score`` and the normalized ``gap_type`` / ``domain`` reuse
:func:`kg_retrievers.gap_scoring.score_gap`, so a gap missing those fields still
exports with the same neutral defaults the scorer applies. Any other original
gap keys pass through unchanged as extra columns, in first-seen order.

Kuzu note: custom gap props (owner, absence_confidence, …) are *not* queryable
columns — a caller reading gaps from the store must ``RETURN`` base columns and
hydrate the rest via ``get_node`` before handing the dicts here.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from kg_retrievers.gap_scoring import score_gap

# Guaranteed leading columns, always emitted (even for an empty gap list) and in
# this order (§15.13). Every export row carries these three keys; further keys
# from the original gap dicts are appended after, in first-seen order.
BASE_COLUMNS: tuple[str, ...] = ("score", "gap_type", "domain")

# RU fallback for a gap without a domain — an empty cell rather than a label,
# so the numeric/text export stays clean for downstream tools.
EMPTY_DOMAIN = ""


def _export_row(gap: dict[str, Any]) -> dict[str, Any]:
    """One flattened export row: original gap keys + computed score/type/domain."""
    scored = score_gap(gap)
    row: dict[str, Any] = dict(gap)  # flatten/copy the original gap dict
    row["score"] = scored.score
    row["gap_type"] = scored.gap_type  # normalized (missing → "неизвестный тип")
    row["domain"] = scored.domain if scored.domain is not None else EMPTY_DOMAIN
    return row


def gap_export_rows(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten ``gaps`` into export-ready row dicts (score + type + domain) (§15.13).

    Each returned dict is a shallow copy of the source gap with three keys added
    or overwritten: the priority ``score`` (from
    :func:`~kg_retrievers.gap_scoring.gap_priority_score` via ``score_gap``), the
    normalized ``gap_type`` and the ``domain`` (empty string when absent). All
    other gap fields are carried through verbatim.
    """
    return [_export_row(gap) for gap in gaps]


def _resolve_columns(
    rows: Sequence[dict[str, Any]], columns: Sequence[str] | None
) -> tuple[str, ...]:
    """Column order for the export: explicit ``columns`` or the discovered default.

    Default order is :data:`BASE_COLUMNS` followed by every other key seen across
    ``rows`` in first-seen order — deterministic for a given input order. With no
    rows this is just :data:`BASE_COLUMNS`, so an empty export still has a header.
    """
    if columns is not None:
        return tuple(columns)
    ordered: list[str] = list(BASE_COLUMNS)
    for row in rows:
        for key in row:
            if key not in ordered:
                ordered.append(key)
    return tuple(ordered)


def _rows_to_csv(rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> str:
    """Render ``rows`` as a CSV document over ``columns`` (RU text written as-is).

    Missing keys become empty cells; extra keys not in ``columns`` are dropped.
    Uses ``\\n`` line endings so the output is stable across platforms.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(columns),
        restval="",  # missing field → empty cell
        extrasaction="ignore",  # drop keys not selected by ``columns``
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def _rows_to_json(rows: Sequence[dict[str, Any]]) -> str:
    """Render ``rows`` as a JSON array; ``ensure_ascii=False`` keeps RU verbatim."""
    return json.dumps([dict(row) for row in rows], ensure_ascii=False, default=str)


def gaps_to_csv(gaps: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    """Export ``gaps`` as a CSV document — header row plus one line per gap (§15.13).

    ``columns`` overrides the column selection/order; by default it is
    :data:`BASE_COLUMNS` plus any other gap keys in first-seen order. An empty
    ``gaps`` list yields the header line only. RU characters are written verbatim.
    """
    rows = gap_export_rows(gaps)
    return _rows_to_csv(rows, _resolve_columns(rows, columns))


def gaps_to_json(gaps: list[dict[str, Any]]) -> str:
    """Export ``gaps`` as a JSON array of export rows, RU preserved verbatim (§15.13).

    ``json.loads(gaps_to_json(gaps)) == gap_export_rows(gaps)`` for JSON-native
    gap values, so the export round-trips losslessly.
    """
    return _rows_to_json(gap_export_rows(gaps))


@dataclass(frozen=True)
class GapExportTable:
    """Export-ready gap table: ordered ``columns`` + flattened ``rows`` (§15.13)."""

    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "columns": list(self.columns),
            "rows": [dict(row) for row in self.rows],
        }

    def to_csv(self) -> str:
        """This table as a CSV document (header + one line per row)."""
        return _rows_to_csv(self.rows, self.columns)

    def to_json(self) -> str:
        """This table's rows as a JSON array (RU preserved verbatim)."""
        return _rows_to_json(self.rows)


def build_gap_export(
    gaps: list[dict[str, Any]], *, columns: list[str] | None = None
) -> GapExportTable:
    """Flatten and column-resolve ``gaps`` into a :class:`GapExportTable` (§15.13)."""
    rows = gap_export_rows(gaps)
    return GapExportTable(columns=_resolve_columns(rows, columns), rows=tuple(rows))

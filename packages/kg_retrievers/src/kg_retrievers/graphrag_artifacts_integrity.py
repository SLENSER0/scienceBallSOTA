"""GraphRAG artifacts integrity — validate the parquet-shaped artifact tables (§11.4).

Проверка целостности артефактов GraphRAG. Before a GraphRAG index can be
queried we must be sure the exported artifact *tables* — ``entities``,
``relationships``, ``text_units``, ``communities`` and ``community_reports`` —
are all present and internally consistent. A missing table, a community report
row that lost a column, an empty summary, or a flat (single-level) hierarchy all
silently degrade global/local search, so this module surfaces them up front.

This is a pure-python guard rail (no graph, no I/O). Tables are passed as a plain
``dict[str, list[dict]]`` — each value a list of row dicts — exactly the shape a
parquet reader (or a temp store dump) yields. :func:`check_artifacts` returns a
frozen :class:`IntegrityReport` carrying the headline counts and a list of
human-readable ``errors`` (RU/EN-friendly stable strings); ``ok`` is True iff
that list is empty.

Hierarchy levels are 0-indexed: a two-level hierarchy (levels ``0`` and ``1``)
reports ``max_level == 1``. A flat set (only level ``0``) fails the
``max_level >= 1`` invariant.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Tables every GraphRAG export must contain (§11.4).
REQUIRED_TABLES = {"entities", "relationships", "text_units", "communities", "community_reports"}
# Columns every ``community_reports`` row must carry (§11.4).
REPORT_COLUMNS = {"community_id", "title", "summary", "level", "rank", "findings"}


@dataclass(frozen=True)
class IntegrityReport:
    """Verdict for one artifact-table set (§11.4).

    ``ok`` is True iff ``errors`` is empty. ``n_communities`` is the row count of
    the ``communities`` table; ``n_reports`` counts only reports with a non-empty
    ``summary``; ``max_level`` is the highest ``level`` seen across report rows
    (0 when none).
    """

    ok: bool
    n_communities: int
    n_reports: int
    max_level: int
    errors: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def _to_int(value: object) -> int | None:
    """Return ``value`` as an int, or None when it is missing/non-numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_nonempty(value: object) -> bool:
    """True when ``value`` is a non-null, non-blank string-ish cell."""
    return value is not None and bool(str(value).strip())


def check_artifacts(tables: dict[str, list[dict]]) -> IntegrityReport:
    """Validate a GraphRAG artifact-table set and return an :class:`IntegrityReport` (§11.4).

    Checks, accumulating a stable error string for each violation:

    - every :data:`REQUIRED_TABLES` key is present (``missing table: X``);
    - every ``community_reports`` row carries all :data:`REPORT_COLUMNS`
      (``community_reports row N: missing column: C``);
    - ``n_communities > 0`` (else ``no communities: n_communities must be > 0``);
    - each report has a non-empty ``summary`` (else ``community_reports row N:
      empty summary``) — only non-empty summaries count toward ``n_reports``;
    - the hierarchy spans at least two levels, i.e. ``max_level >= 1``.

    ``ok`` is True iff no error was recorded.
    """
    errors: list[str] = []

    for table in sorted(REQUIRED_TABLES):
        if table not in tables:
            errors.append(f"missing table: {table}")

    communities = tables.get("communities") or []
    reports = tables.get("community_reports") or []
    n_communities = len(communities)
    if n_communities <= 0:
        errors.append("no communities: n_communities must be > 0")

    n_reports = 0
    levels: list[int] = []
    for idx, row in enumerate(reports):
        for col in sorted(REPORT_COLUMNS - set(row.keys())):
            errors.append(f"community_reports row {idx}: missing column: {col}")
        if _is_nonempty(row.get("summary")):
            n_reports += 1
        else:
            errors.append(f"community_reports row {idx}: empty summary")
        lvl = _to_int(row.get("level"))
        if lvl is not None:
            levels.append(lvl)

    max_level = max(levels) if levels else 0
    if max_level < 1:
        errors.append(f"flat hierarchy: max_level {max_level} must be >= 1")

    return IntegrityReport(
        ok=not errors,
        n_communities=n_communities,
        n_reports=n_reports,
        max_level=max_level,
        errors=errors,
    )

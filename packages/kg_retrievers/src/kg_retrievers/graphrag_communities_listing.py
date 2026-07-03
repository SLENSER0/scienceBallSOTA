"""GraphRAG community listing and detail views (§11.9).

GraphRAG produces one *community report* per detected community across a hierarchy of
levels (уровни иерархии): level ``0`` holds fine-grained, entity-level clusters while
higher levels roll those up into broad, global summaries. A report carries a ``title``,
a ``summary``, a list of ``findings``, the ``cited_doc_ids`` it draws on and its
``sub_communities``. This module offers two read-side views over a list of such reports:

* :func:`list_communities` — a paginated, sorted *index* of communities. It can filter
  to a single ``level`` (уровень), sorts by ``rank`` descending (most important first)
  with ``community_id`` ascending as a stable tiebreak, and slices via ``offset`` /
  ``limit``. The reported ``total`` is the *pre-pagination* filtered count so callers can
  build page controls independent of the current window.
* :func:`community_detail` — the full report for one ``community_id`` (summary, findings,
  cited docs, sub-communities), or ``None`` when the id is unknown.

Both views are pure functions over plain report dicts (обычные словари), so they compose
with any store or export layer without a live graph connection.
"""

from __future__ import annotations

from dataclasses import dataclass

# Default page size for :func:`list_communities` when the caller does not override it.
_DEFAULT_LIMIT: int = 50


@dataclass(frozen=True)
class CommunityListItem:
    """One row in a community index (§11.9).

    ``community_id`` — stable id of the community; ``title`` — its human-readable label;
    ``level`` — position in the hierarchy (``0`` = finest); ``rank`` — importance score
    used for ordering (выше = важнее).
    """

    community_id: str
    title: str
    level: int
    rank: float

    def as_dict(self) -> dict:
        return {
            "community_id": self.community_id,
            "title": self.title,
            "level": self.level,
            "rank": self.rank,
        }


@dataclass(frozen=True)
class CommunityListing:
    """A paginated listing of communities (§11.9).

    ``items`` — the current page of rows; ``total`` — the pre-pagination filtered count
    (независимо от ``limit``); ``level_filter`` — the level filter that was applied, or
    ``None`` when all levels were included.
    """

    items: list[CommunityListItem]
    total: int
    level_filter: int | None

    def as_dict(self) -> dict:
        return {
            "items": [item.as_dict() for item in self.items],
            "total": self.total,
            "level_filter": self.level_filter,
        }


def _to_item(report: dict) -> CommunityListItem:
    """Project a raw community ``report`` dict onto a lightweight index row."""
    return CommunityListItem(
        community_id=str(report.get("community_id", "")),
        title=str(report.get("title", "")),
        level=int(report.get("level", 0)),
        rank=float(report.get("rank", 0.0)),
    )


def list_communities(
    reports: list[dict],
    *,
    level: int | None = None,
    limit: int = _DEFAULT_LIMIT,
    offset: int = 0,
) -> CommunityListing:
    """Build a sorted, paginated community index from ``reports`` (§11.9).

    When ``level`` is given, only reports at that hierarchy level are kept; ``total`` then
    reflects that filtered count. Rows are ordered by ``rank`` descending (most important
    first), breaking ties by ``community_id`` ascending for a stable page. Pagination
    drops the first ``offset`` rows and keeps at most ``limit`` of the rest; ``total`` is
    the pre-pagination filtered count so it never depends on ``offset`` or ``limit``.
    """
    filtered = [r for r in reports if level is None or int(r.get("level", 0)) == level]
    items = [_to_item(r) for r in filtered]
    items.sort(key=lambda it: (-it.rank, it.community_id))

    total = len(items)
    start = max(0, offset)
    page = items[start : start + limit] if limit >= 0 else items[start:]

    return CommunityListing(items=page, total=total, level_filter=level)


def community_detail(reports: list[dict], community_id: str) -> dict | None:
    """Return the full community report for ``community_id`` or ``None`` (§11.9).

    Scans ``reports`` for the first entry whose ``community_id`` matches and returns it
    unchanged (summary/findings/cited_doc_ids/sub_communities included). Returns ``None``
    when no report carries that id, so an unknown lookup never raises.
    """
    for report in reports:
        if str(report.get("community_id", "")) == community_id:
            return report
    return None

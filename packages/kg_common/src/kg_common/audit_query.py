"""Admin audit-log query — filter + pagination — фильтр журнала аудита (§19.5).

The admin console must let an operator slice the audit trail by *who* did it
(``actor_id``), *what* they did (``action``), *what kind* of object was touched
(``target_type``) and *when* (``ts_from`` / ``ts_to``), then page through the
result newest-first («фильтрация и постраничный вывод журнала аудита»).

Everything here is deterministic and side-effect free:

* No wall-clock and no I/O — rows are supplied by the caller as plain mappings,
  so the same inputs always yield the same page.
* No mutation — :func:`query` reads the input rows and returns a fresh
  :class:`AuditPage`; the caller's sequence and row mappings are never touched.

A filter field set to ``None`` means «не фильтровать по этому полю»: an all-``None``
:class:`AuditFilter` matches every row. Timestamp bounds ``ts_from`` / ``ts_to``
are *inclusive*.

Public API:

* :class:`AuditFilter` — frozen filter spec with :meth:`AuditFilter.as_dict`.
* :class:`AuditPage`   — frozen page of results with :meth:`AuditPage.as_dict`.
* :func:`matches`      — does a single row satisfy a filter?
* :func:`query`        — sort matches by ``ts`` descending, then paginate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "AuditFilter",
    "AuditPage",
    "matches",
    "query",
]


@dataclass(frozen=True)
class AuditFilter:
    """An immutable audit-log filter spec — спецификация фильтра (§19.5).

    Each field is optional: ``None`` means «этот критерий не применяется». The
    equality fields (``actor_id`` / ``action`` / ``target_type``) must match the
    row exactly, while ``ts_from`` / ``ts_to`` are *inclusive* lower / upper
    bounds on the row's ``ts``. All supplied criteria combine with logical AND.
    """

    actor_id: str | None = None
    action: str | None = None
    target_type: str | None = None
    ts_from: float | None = None
    ts_to: float | None = None

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly view of the filter — представление фильтра (§19.5).

        Returns all five criteria, ``None`` included, so a serialized filter is
        self-describing and round-trips back through the constructor.
        """
        return {
            "actor_id": self.actor_id,
            "action": self.action,
            "target_type": self.target_type,
            "ts_from": self.ts_from,
            "ts_to": self.ts_to,
        }


@dataclass(frozen=True)
class AuditPage:
    """An immutable page of audit rows — страница результатов (§19.5).

    ``rows`` is the (already sorted + sliced) page, ``total`` the full number of
    rows that matched *before* pagination, and ``offset`` / ``limit`` the window
    that produced this page («total отражает все совпадения, а не длину страницы»).
    """

    rows: tuple[dict[str, Any], ...]
    total: int
    offset: int
    limit: int

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly view of the page — представление страницы (§19.5).

        ``rows`` is materialized as a ``list`` of plain ``dict`` copies so the
        result is safe to serialize and never aliases the stored tuple.
        """
        return {
            "rows": [dict(row) for row in self.rows],
            "total": self.total,
            "offset": self.offset,
            "limit": self.limit,
        }


def matches(row: Mapping[str, Any], flt: AuditFilter) -> bool:
    """Does *row* satisfy *flt*? — удовлетворяет ли запись фильтру (§19.5).

    Every non-``None`` filter field must hold: the equality fields must equal the
    row's corresponding value, and the row's ``ts`` must fall within the inclusive
    ``[ts_from, ts_to]`` bounds. A field left as ``None`` imposes no constraint, so
    an all-``None`` filter matches every row. Criteria combine with logical AND.
    """
    if flt.actor_id is not None and row.get("actor_id") != flt.actor_id:
        return False
    if flt.action is not None and row.get("action") != flt.action:
        return False
    if flt.target_type is not None and row.get("target_type") != flt.target_type:
        return False
    if flt.ts_from is not None or flt.ts_to is not None:
        ts = row.get("ts")
        if flt.ts_from is not None and ts < flt.ts_from:
            return False
        if flt.ts_to is not None and ts > flt.ts_to:
            return False
    return True


def query(
    rows: Sequence[Mapping[str, Any]],
    flt: AuditFilter,
    *,
    offset: int = 0,
    limit: int = 50,
) -> AuditPage:
    """Filter, sort newest-first, then paginate — выборка страницы (§19.5).

    Keeps only the rows that satisfy *flt*, sorts the survivors by ``ts``
    *descending* (newest first) and slices out the ``[offset, offset + limit)``
    window. The returned :class:`AuditPage` carries the full match ``total`` — the
    count *before* pagination — alongside the requested ``offset`` / ``limit``, so
    a caller can render "showing N of total". Matched rows are copied into fresh
    ``dict`` s; the input sequence and its mappings are never mutated.
    """
    hits = [dict(row) for row in rows if matches(row, flt)]
    hits.sort(key=lambda r: r.get("ts"), reverse=True)
    total = len(hits)
    page = tuple(hits[offset : offset + limit])
    return AuditPage(rows=page, total=total, offset=offset, limit=limit)

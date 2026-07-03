"""Gap trends across scan runs — opened / closed / net change over time (§15.11).

Each scan run of the gap analyzer (:mod:`kg_retrievers.gap_analysis`, §15) leaves a
*snapshot* of the open ``Gap`` set. §15.11 rolls an **ordered** series of those
snapshots into a single trend a curator can read at a glance: how many gaps opened,
how many closed, and whether the backlog is shrinking or growing. Тренд пропусков
по прогонам сканера: открыто / закрыто / чистое изменение.

A snapshot is a plain mapping ``{run_id, created_at, gap_ids: list}`` — no graph is
touched here, so this module is **pure Python** and trivially unit-testable. Each
entry of ``gap_ids`` is either a bare id string or a mapping ``{id, gap_type}``; the
optional ``gap_type`` feeds :attr:`GapTrend.by_type_delta` and otherwise falls back
to :data:`UNKNOWN_TYPE`.

Per **step** (transition ``prev -> cur``) we count *opened* ids (new vs the previous
snapshot) and *closed* ids (disappeared), so a gap that appears once and then stays
gone is counted **once**. The step *net change* is ``opened - closed``, which
telescopes to ``|last set| - |first set|`` over the whole series — the reported
:attr:`GapTrend.net_change`. :func:`trend_direction` reads that sign: a shrinking
backlog is *improving*, a growing one *worsening*, no change *stable*.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# Direction verdicts (§15.11) — сокращается / растёт / без изменений.
DIR_IMPROVING = "improving"
DIR_WORSENING = "worsening"
DIR_STABLE = "stable"

# RU fallback bucket for a gap id that carries no ``gap_type`` (matches §15.6).
UNKNOWN_TYPE = "неизвестный тип"


@dataclass(frozen=True)
class GapTrend:
    """Aggregated gap trend across an ordered series of scan snapshots (§15.11).

    ``points`` is the per-step timeline (one dict per input snapshot, in order);
    ``opened`` / ``closed`` are the totals of open/close events across all steps;
    ``net_change`` is ``opened - closed`` (== gaps in the last snapshot minus the
    first); ``by_type_delta`` breaks that net change down by ``gap_type`` (zero
    deltas omitted, so its values always sum to ``net_change``).
    """

    points: list[dict[str, Any]] = field(default_factory=list)
    opened: int = 0
    closed: int = 0
    net_change: int = 0
    by_type_delta: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "points": [dict(p) for p in self.points],
            "opened": self.opened,
            "closed": self.closed,
            "net_change": self.net_change,
            "by_type_delta": dict(self.by_type_delta),
        }


def _entry_id(entry: Any) -> str:
    """Gap id of a ``gap_ids`` entry — a bare string or a mapping's ``id`` (§15.11)."""
    if isinstance(entry, Mapping):
        return str(entry.get("id", ""))
    return str(entry)


def _entry_type(entry: Any) -> str:
    """Gap type of an entry — a mapping's ``gap_type``, else :data:`UNKNOWN_TYPE`."""
    if isinstance(entry, Mapping):
        gtype = entry.get("gap_type")
        if isinstance(gtype, str) and gtype.strip():
            return gtype.strip()
    return UNKNOWN_TYPE


def _gap_map(snapshot: Mapping[str, Any]) -> dict[str, str]:
    """Map ``id -> gap_type`` for one snapshot, de-duplicating repeated ids (§15.11)."""
    gmap: dict[str, str] = {}
    for entry in snapshot.get("gap_ids") or []:
        gid = _entry_id(entry)
        if gid:
            gmap[gid] = _entry_type(entry)
    return gmap


def _point(snapshot: Mapping[str, Any], gaps: int, opened: int, closed: int) -> dict[str, Any]:
    """One timeline row: run identity + this step's opened / closed / net change."""
    return {
        "run_id": snapshot.get("run_id"),
        "created_at": snapshot.get("created_at"),
        "gaps": gaps,
        "opened": opened,
        "closed": closed,
        "net_change": opened - closed,
    }


def compute_trends(snapshots: Sequence[Mapping[str, Any]]) -> GapTrend:
    """Aggregate an ordered series of gap snapshots into a :class:`GapTrend` (§15.11).

    Snapshots are consumed in the order given (the caller is trusted to have sorted
    them by ``created_at``). For each transition ``prev -> cur`` we count ids that
    appeared (*opened*) and disappeared (*closed*); the first snapshot has no
    predecessor and so contributes zeros. Totals accumulate across steps, and
    ``by_type_delta`` sums each step's ``opened - closed`` per ``gap_type`` (zero
    deltas dropped). An empty series yields an all-zero trend; a single snapshot
    yields one point with zeroed deltas.
    """
    points: list[dict[str, Any]] = []
    opened_total = 0
    closed_total = 0
    by_type: dict[str, int] = {}
    prev_ids: set[str] | None = None
    prev_map: dict[str, str] = {}
    for snapshot in snapshots:
        gmap = _gap_map(snapshot)
        cur_ids = set(gmap)
        if prev_ids is None:
            opened = closed = 0
        else:
            opened_ids = cur_ids - prev_ids
            closed_ids = prev_ids - cur_ids
            opened, closed = len(opened_ids), len(closed_ids)
            opened_total += opened
            closed_total += closed
            for gid in opened_ids:
                gtype = gmap[gid]
                by_type[gtype] = by_type.get(gtype, 0) + 1
            for gid in closed_ids:
                gtype = prev_map[gid]
                by_type[gtype] = by_type.get(gtype, 0) - 1
        points.append(_point(snapshot, len(cur_ids), opened, closed))
        prev_ids, prev_map = cur_ids, gmap
    by_type_delta = {t: d for t, d in sorted(by_type.items()) if d != 0}
    return GapTrend(
        points=points,
        opened=opened_total,
        closed=closed_total,
        net_change=opened_total - closed_total,
        by_type_delta=by_type_delta,
    )


def trend_direction(trend: GapTrend) -> str:
    """Verdict on a trend from its net change — improving / worsening / stable (§15.11).

    A negative :attr:`GapTrend.net_change` means the backlog shrank (*improving*), a
    positive one that it grew (*worsening*), and zero that it held (*stable*).
    """
    if trend.net_change < 0:
        return DIR_IMPROVING
    if trend.net_change > 0:
        return DIR_WORSENING
    return DIR_STABLE

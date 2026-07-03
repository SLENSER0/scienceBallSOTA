"""Team & lab activity aggregation for the dashboard (§24.15).

Дашборды/активность команд: сводка активности по лабораториям и экспертам —
публикации / отчёты / эксперименты / curation. Given a flat event log, this
groups events by ``(entity_id, entity_kind)`` and tallies them per
``activity_type``, so the team-activity dashboard can show, per lab or expert,
how many publications / reports / experiments / curation actions happened and
when the most recent one landed.

Everything is pure-data: events are plain dicts (``entity_id``,
``entity_kind``, ``activity_type``, ``date`` as ISO ``YYYY-MM-DD``). An optional
``since`` lower bound drops older events *before* tallying, so the counts, the
``total`` and the ``latest_date`` all reflect only the retained window.
Unrecognized ``activity_type`` values are tallied under their own key (no
whitelist). Summaries are sorted by ``total`` desc, ties broken by
``entity_id`` asc.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from kg_common import get_logger

_log = get_logger("team_activity")


@dataclass(frozen=True)
class ActivitySummary:
    """Read-only activity roll-up for one lab / expert (§24.15).

    - ``entity_id`` — the lab or expert this summary describes;
    - ``entity_kind`` — what kind of entity it is (e.g. ``"lab"`` / ``"expert"``);
    - ``counts`` — per-``activity_type`` tally (publications / reports / etc.);
    - ``total`` — sum of ``counts.values()`` (retained events for this entity);
    - ``latest_date`` — max ISO date string across retained events, or ``None``.
    """

    entity_id: str
    entity_kind: str
    counts: dict[str, int]
    total: int
    latest_date: str | None

    def as_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "entity_kind": self.entity_kind,
            "counts": dict(self.counts),
            "total": self.total,
            "latest_date": self.latest_date,
        }


def summarize_activity(events: list[dict], *, since: str | None = None) -> list[ActivitySummary]:
    """Aggregate ``events`` into per-entity :class:`ActivitySummary` rows (§24.15).

    Each event is a dict with ``entity_id``, ``entity_kind``, ``activity_type``
    and ``date`` (ISO ``YYYY-MM-DD``). Events whose ``date`` is strictly before
    ``since`` are excluded. Remaining events are grouped by
    ``(entity_id, entity_kind)``; ``counts`` tallies each ``activity_type`` (any
    value, recognized or not), ``total`` is the sum of those tallies, and
    ``latest_date`` is the newest ISO date in the group. Results are sorted by
    ``total`` desc, then ``entity_id`` asc. Empty input yields ``[]``.
    """
    tallies: dict[tuple[str, str], Counter[str]] = {}
    latest: dict[tuple[str, str], str] = {}
    for event in events:
        date = str(event["date"])
        if since is not None and date < since:
            continue
        key = (str(event["entity_id"]), str(event["entity_kind"]))
        activity_type = str(event["activity_type"])
        tallies.setdefault(key, Counter())[activity_type] += 1
        current = latest.get(key)
        if current is None or date > current:
            latest[key] = date

    summaries = [
        ActivitySummary(
            entity_id=entity_id,
            entity_kind=entity_kind,
            counts=dict(counter),
            total=sum(counter.values()),
            latest_date=latest[(entity_id, entity_kind)],
        )
        for (entity_id, entity_kind), counter in tallies.items()
    ]
    summaries.sort(key=lambda s: (-s.total, s.entity_id))
    _log.info("team_activity.summarize", n_events=len(events), n_entities=len(summaries))
    return summaries

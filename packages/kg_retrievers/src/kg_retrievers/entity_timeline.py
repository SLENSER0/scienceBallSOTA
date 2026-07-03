"""Entity-detail timeline view-model (§17.11 / §5.2.4).

Folds heterogeneous *dated* events about a single entity — papers (``year``),
experiments (``date``) and curation events (``created_at``) — into one
chronological timeline for the §5.2.4 timeline chart. The retrievers already
surface these records separately; nothing merges them into a single sortable
stream, which this pure builder provides.

Сворачивает разнородные датированные события одной сущности (статьи, опыты,
курирование) в единый хронологический таймлайн для графика §5.2.4.

Normalisation and ordering rules:
- a bare year ``'YYYY'`` (str or int) becomes ``'YYYY-01-01'``; partial ISO
  dates such as ``'2021-05'`` are kept verbatim in the ``date`` field;
- events sort ascending by ISO date; ties break by :data:`EVENT_KINDS` kind
  order (``paper`` < ``experiment`` < ``curation``) then by ``ref_id``;
- ``span_start`` / ``span_end`` are the ``date`` fields of the first / last
  events, or ``None`` when there are no events.

Pure, read-only data logic — no store access.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Canonical event kinds and their tie-break order (§17.11).
_KIND_ORDER: tuple[str, ...] = ("paper", "experiment", "curation")
EVENT_KINDS: frozenset[str] = frozenset(_KIND_ORDER)


@dataclass(frozen=True)
class EntityTimeline:
    """Chronological timeline of one entity's dated events (§17.11).

    - ``events`` — ascending tuple of ``{kind, date, label, ref_id}`` dicts;
    - ``span_start`` — ``date`` of the earliest event, or ``None`` if empty;
    - ``span_end`` — ``date`` of the latest event, or ``None`` if empty.
    """

    events: tuple[dict[str, str], ...]
    span_start: str | None
    span_end: str | None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly mapping with camelCase span keys."""
        return {
            "events": [dict(event) for event in self.events],
            "spanStart": self.span_start,
            "spanEnd": self.span_end,
        }


def _normalise_date(raw: object) -> str:
    """Normalise a raw date; a bare year ``'YYYY'``/int -> ``'YYYY-01-01'``.

    Partial or full ISO strings (``'2021-05'``, ``'2020-03-01'``) pass through
    unchanged. Non-year integers are rendered as their decimal string.
    """
    text = str(raw).strip()
    if text.isdigit() and len(text) == 4:
        return f"{text}-01-01"
    return text


def _sort_key(event: Mapping[str, str]) -> tuple[str, int, str]:
    """Build a stable sort key: padded ISO date, kind order, then ``ref_id``."""
    parts = event["date"].split("-")
    year = parts[0]
    month = parts[1] if len(parts) > 1 else "01"
    day = parts[2] if len(parts) > 2 else "01"
    padded = f"{year.zfill(4)}-{month.zfill(2)}-{day.zfill(2)}"
    try:
        kind_rank = _KIND_ORDER.index(event["kind"])
    except ValueError:
        kind_rank = len(_KIND_ORDER)
    return (padded, kind_rank, event["ref_id"])


def _ref_id(record: Mapping[str, object]) -> str:
    """Read an event's ref_id, preferring ``ref_id`` then ``id``."""
    value = record.get("ref_id", record.get("id", ""))
    return str(value)


def _label(record: Mapping[str, object]) -> str:
    """Read a human label, preferring ``label`` then ``title``/``name``."""
    for key in ("label", "title", "name"):
        if key in record and record[key] is not None:
            return str(record[key])
    return ""


def _event(kind: str, raw_date: object, record: Mapping[str, object]) -> dict[str, str]:
    """Assemble one normalised timeline event dict."""
    return {
        "kind": kind,
        "date": _normalise_date(raw_date),
        "label": _label(record),
        "ref_id": _ref_id(record),
    }


def build_entity_timeline(
    papers: Sequence[Mapping[str, object]],
    experiments: Sequence[Mapping[str, object]],
    curation_events: Sequence[Mapping[str, object]],
) -> EntityTimeline:
    """Fold papers / experiments / curation events into an :class:`EntityTimeline`.

    Papers are dated by ``year``, experiments by ``date`` and curation events by
    ``created_at``. Events are normalised, then sorted ascending by ISO date with
    ties broken by kind order and ``ref_id``. ``span_start`` / ``span_end`` are
    the first / last event ``date`` fields, or ``None`` when there are no events.
    """
    events: list[dict[str, str]] = []
    events.extend(_event("paper", record.get("year"), record) for record in papers)
    events.extend(_event("experiment", record.get("date"), record) for record in experiments)
    events.extend(
        _event("curation", record.get("created_at"), record) for record in curation_events
    )

    events.sort(key=_sort_key)

    if not events:
        return EntityTimeline(events=(), span_start=None, span_end=None)

    return EntityTimeline(
        events=tuple(events),
        span_start=events[0]["date"],
        span_end=events[-1]["date"],
    )

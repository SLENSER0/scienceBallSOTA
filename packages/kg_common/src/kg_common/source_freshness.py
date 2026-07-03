"""Source freshness / staleness classification — свежесть источников (§10.7).

The source-catalog card (§10.7) shows, for every registered source, *how fresh*
its data is: when was it last ingested, and does that make it ``fresh``,
``aging`` or ``stale``? A source that was never ingested is ``unknown``. This
module turns a «last-ingest timestamp» plus an «as-of» clock into that verdict
without touching any store or wall-clock — the caller passes ``as_of``
explicitly so classification is fully deterministic and hand-checkable.

Levels («уровни свежести»), by age in whole days:

* ``fresh``   — ``age_days <= fresh_days`` (default ``30``);
* ``aging``   — ``fresh_days < age_days <= stale_days`` (default ``180``);
* ``stale``   — ``age_days > stale_days``;
* ``unknown`` — no ingest timestamp at all («никогда не загружался»).

Boundaries are inclusive on the *fresh* / *aging* side: exactly ``fresh_days``
old is still ``fresh``, exactly ``stale_days`` old is still ``aging``.

Public API:

* :data:`LEVELS`     — the four levels in worsening order.
* :class:`Freshness` — frozen ``(source_id, last_ingest_at, age_days, level)``
  record with :meth:`Freshness.as_dict`.
* :func:`classify`   — build a :class:`Freshness` from timestamps.
* :func:`rank`       — map a :class:`Freshness` to a severity rank (``0..3``).
* :func:`stalest`    — pick the worst :class:`Freshness` from a collection.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

__all__ = [
    "LEVELS",
    "Freshness",
    "classify",
    "rank",
    "stalest",
]

#: The four freshness levels in worsening order — уровни по возрастанию «беды».
LEVELS: tuple[str, ...] = ("fresh", "aging", "stale", "unknown")

#: Severity rank per level — чем выше, тем «хуже» (§10.7).
_RANK: dict[str, int] = {"fresh": 0, "aging": 1, "stale": 2, "unknown": 3}


@dataclass(frozen=True, slots=True)
class Freshness:
    """Immutable freshness verdict for one source — вердикт по источнику (§10.7).

    ``source_id`` identifies the source; ``last_ingest_at`` is the ISO-8601
    timestamp of the last ingest (or ``None`` if it was never ingested);
    ``age_days`` is the whole-day age at the as-of moment (``None`` when
    unknown); ``level`` is one of :data:`LEVELS`. A plain frozen value so it can
    be hashed, compared and serialized for the catalog card.
    """

    source_id: str
    last_ingest_at: str | None
    age_days: int | None
    level: str

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — строка карточки источника (§10.7)."""
        return {
            "source_id": self.source_id,
            "last_ingest_at": self.last_ingest_at,
            "age_days": self.age_days,
            "level": self.level,
        }


def classify(
    source_id: str,
    last_ingest_at: datetime | None,
    as_of: datetime,
    fresh_days: int = 30,
    stale_days: int = 180,
) -> Freshness:
    """Classify a source's freshness at ``as_of`` — классифицировать (§10.7).

    ``last_ingest_at`` is when the source was last ingested; ``None`` means it
    never was, yielding an ``unknown`` verdict with ``age_days is None``.
    Otherwise the age is ``(as_of - last_ingest_at).days`` (whole days, floored)
    and the level is ``fresh`` when ``age <= fresh_days``, ``aging`` when
    ``age <= stale_days``, else ``stale``. Both bounds are inclusive on the
    fresher side. ``last_ingest_at`` is stored as its ISO-8601 string.
    """
    if last_ingest_at is None:
        return Freshness(source_id=source_id, last_ingest_at=None, age_days=None, level="unknown")
    age_days = (as_of - last_ingest_at).days
    if age_days <= fresh_days:
        level = "fresh"
    elif age_days <= stale_days:
        level = "aging"
    else:
        level = "stale"
    return Freshness(
        source_id=source_id,
        last_ingest_at=last_ingest_at.isoformat(),
        age_days=age_days,
        level=level,
    )


def rank(freshness: Freshness) -> int:
    """Severity rank of a verdict — ранг «беды» (§10.7).

    Maps the level to ``fresh=0``, ``aging=1``, ``stale=2``, ``unknown=3`` so
    higher means «нужнее обновить». An unrecognized level is a programming error
    and raises :class:`KeyError`.
    """
    return _RANK[freshness.level]


def stalest(items: Iterable[Freshness]) -> Freshness | None:
    """Pick the worst verdict — самый несвежий источник (§10.7).

    Orders by :func:`rank` (higher is worse) and breaks ties by larger
    ``age_days`` — a missing ``age_days`` (``unknown``) counts as ``-1`` so a
    genuinely stale item with a real age wins a tie against… well, ``unknown``
    always outranks by rank anyway. Returns ``None`` for an empty iterable.
    """
    best: Freshness | None = None
    best_key: tuple[int, int] | None = None
    for item in items:
        key = (rank(item), item.age_days if item.age_days is not None else -1)
        if best_key is None or key > best_key:
            best, best_key = item, key
    return best

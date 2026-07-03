"""Sensor idempotent cursor — идемпотентный курсор сенсора (§9.6).

A *sensor* polls some external source (a directory listing, an API page, a table
partition) and periodically re-runs over an overlapping window of candidate
tokens. To stay **idempotent** it must remember how far it has already advanced
and only act on tokens it has never seen — otherwise a re-poll would re-emit work
(«повторная обработка»).

This module models that «watermark» as a small frozen value plus two pure
functions. Everything is deterministic and side-effect free — no wall-clock, no
I/O, no persistence — so a scheduler can checkpoint the cursor however it likes.

Ordering is **lexicographic** over the raw string tokens. This is deliberate: the
monotonic tokens a sensor sees in practice — ISO-8601 timestamps/dates
(``2026-07-01``), zero-padded sequence numbers, ULIDs — all sort correctly under
plain string comparison, so no token-type parsing is needed («монотонные
токены»). The empty string ``""`` is the natural minimum, so a fresh cursor at
position ``""`` treats *every* candidate as new.

Public API:

* :class:`SensorCursor` — frozen ``(name, position, seen_count)`` record with
  :meth:`SensorCursor.as_dict` / :meth:`SensorCursor.from_dict` roundtrip.
* :func:`new_items`      — candidates strictly greater than a position, in input
  order.
* :func:`advance_cursor` — advance a cursor past a fresh batch of candidates.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "SensorCursor",
    "advance_cursor",
    "new_items",
]


@dataclass(frozen=True, slots=True)
class SensorCursor:
    """Immutable sensor watermark — водяной знак сенсора (§9.6).

    ``name`` identifies the sensor; ``position`` is the highest token already
    processed (the empty string ``""`` means «ещё ничего не видели»);
    ``seen_count`` is the running total of items the cursor has advanced past.
    The record is a plain frozen value so it can be hashed, compared and
    serialized.
    """

    name: str
    position: str
    seen_count: int = 0

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — сериализация курсора (§9.6)."""
        return {
            "name": self.name,
            "position": self.position,
            "seen_count": self.seen_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> SensorCursor:
        """Rebuild a cursor from :meth:`as_dict` output — разбор курсора (§9.6).

        Roundtrips exactly: ``SensorCursor.from_dict(c.as_dict()) == c``.
        """
        return cls(
            name=str(data["name"]),
            position=str(data["position"]),
            seen_count=int(data["seen_count"]),  # type: ignore[arg-type]
        )


def new_items(position: str, candidates: Sequence[str]) -> tuple[str, ...]:
    """Candidates strictly greater than ``position`` — новые токены (§9.6).

    Returns, **in input order**, every candidate that sorts strictly after
    ``position`` under lexicographic (string) comparison. Because monotonic
    tokens (ISO dates, zero-padded counters, ULIDs) already sort correctly as
    strings, this is exactly «что появилось после водяного знака». A candidate
    equal to ``position`` is *not* new (idempotency: it was the last one seen).
    """
    return tuple(item for item in candidates if item > position)


def advance_cursor(cursor: SensorCursor, candidates: Sequence[str]) -> SensorCursor:
    """Advance ``cursor`` past the fresh candidates — сдвинуть курсор (§9.6).

    Computes :func:`new_items` for ``cursor.position``; if there are none the
    cursor is returned unchanged (idempotent re-poll — «ничего нового»).
    Otherwise the new position is the maximum of the old position and the new
    items, and ``seen_count`` grows by the number of new items. ``name`` is
    preserved.
    """
    fresh = new_items(cursor.position, candidates)
    if not fresh:
        return cursor
    new_position = max((cursor.position, *fresh))
    return SensorCursor(
        name=cursor.name,
        position=new_position,
        seen_count=cursor.seen_count + len(fresh),
    )

"""Incremental-sync cursor state — курсор инкрементальной синхронизации (§20.4).

Connectors (ELN, LIMS, instrument feeds) pull records in modified-order and must
remember *how far* they got so the next run only re-reads what changed. This
module models that watermark as a frozen :class:`SyncCursor` keyed by ``system``,
plus three pure helpers over ISO-8601 ``modified_at`` timestamps
(§20.5/§20.11):

* :func:`is_newer`      — is a record past the cursor? An empty cursor («пустой
  курсор») is a cold start, so *everything* is newer.
* :func:`advance`       — fold one record into the cursor, bumping either the
  synced or skipped counter and moving the watermark forward monotonically.
* :func:`merge_cursors` — combine two cursors for the *same* system (e.g. two
  shards / retries), summing counters and taking the later watermark.

Timestamps are compared lexicographically: for zero-padded ISO-8601 strings this
matches chronological order, so no parsing is needed. Everything here is
deterministic and side-effect free; :class:`SyncCursor` is immutable.

Public API:

* :class:`SyncCursor` — frozen watermark with :meth:`SyncCursor.as_dict`.
* :func:`is_newer`, :func:`advance`, :func:`merge_cursors`.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "SyncCursor",
    "advance",
    "is_newer",
    "merge_cursors",
]


@dataclass(frozen=True, slots=True)
class SyncCursor:
    """Immutable sync watermark — неизменяемый курсор синхронизации (§20.4).

    ``last_cursor`` is the highest ``modified_at`` seen so far (ISO-8601, or the
    empty string on a cold start). ``records_synced`` / ``records_skipped`` count
    records folded in via :func:`advance`.
    """

    system: str
    last_cursor: str
    records_synced: int
    records_skipped: int

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — курсор как словарь (§20.4)."""
        return {
            "system": self.system,
            "last_cursor": self.last_cursor,
            "records_synced": self.records_synced,
            "records_skipped": self.records_skipped,
        }


def is_newer(record_ts: str, cursor: str) -> bool:
    """Is ``record_ts`` past ``cursor``? — новее ли запись курсора (§20.5).

    An empty ``cursor`` marks a cold start («холодный старт»), so any record is
    considered newer. Otherwise ISO-8601 strings are compared lexicographically,
    which matches chronological order for zero-padded timestamps.
    """
    if not cursor:
        return True
    return record_ts > cursor


def advance(cursor: SyncCursor, record_ts: str, *, synced: bool = True) -> SyncCursor:
    """Fold one record into ``cursor`` — продвинуть курсор на запись (§20.11).

    Returns a *new* frozen cursor whose ``last_cursor`` is the later of the old
    watermark and ``record_ts`` (monotonic — never moves backward), and with
    exactly one counter incremented: ``records_synced`` when ``synced`` is
    ``True``, otherwise ``records_skipped``.
    """
    return SyncCursor(
        system=cursor.system,
        last_cursor=max(cursor.last_cursor, record_ts),
        records_synced=cursor.records_synced + (1 if synced else 0),
        records_skipped=cursor.records_skipped + (0 if synced else 1),
    )


def merge_cursors(a: SyncCursor, b: SyncCursor) -> SyncCursor:
    """Combine two cursors for the same system — слить два курсора (§20.4).

    Sums the synced/skipped counters and takes the later ``last_cursor``. Raises
    :class:`ValueError` if the cursors belong to different systems, since their
    watermarks are not comparable.
    """
    if a.system != b.system:
        raise ValueError(f"cannot merge cursors of different systems: {a.system!r} != {b.system!r}")
    return SyncCursor(
        system=a.system,
        last_cursor=max(a.last_cursor, b.last_cursor),
        records_synced=a.records_synced + b.records_synced,
        records_skipped=a.records_skipped + b.records_skipped,
    )

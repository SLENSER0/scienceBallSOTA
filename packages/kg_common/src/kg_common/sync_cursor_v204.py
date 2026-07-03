"""Incremental-sync cursor over a timestamp watermark — курсор инкрементальной
синхронизации по возрастающему полю времени (§20.4/§20.5).

A connector pulls records ordered by a monotonically increasing timestamp field
(e.g. ``modified_at``) and remembers *how far* it got so the next run only
re-reads what changed. This module models that watermark as a frozen
:class:`SyncCursor` keyed by ``source_id`` plus the name of the ``cursor_field``,
and two pure helpers (§20.5):

* :func:`filter_new` — keep only records strictly past the cursor. A ``None``
  ``cursor_value`` means a cold start («холодный старт»), so *all* records pass.
* :func:`advance`    — fold a batch into a new cursor, moving ``cursor_value`` to
  the max ``cursor_field`` seen (unchanged on an empty batch) and stamping
  ``last_synced_at``.

Timestamps are compared lexicographically via ``str(...)``: for zero-padded
ISO-8601 strings this matches chronological order, so no parsing is needed. The
comparison is strictly-greater, so a record whose value equals the boundary is
excluded (it was already synced). Everything is deterministic and side-effect
free; :class:`SyncCursor` is immutable and the original record dicts are returned
by identity.

Public API:

* :class:`SyncCursor` — frozen watermark with :meth:`SyncCursor.as_dict`.
* :func:`filter_new`, :func:`advance`.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "SyncCursor",
    "advance",
    "filter_new",
]


@dataclass(frozen=True, slots=True)
class SyncCursor:
    """Immutable incremental-sync watermark — неизменяемый курсор (§20.4).

    ``cursor_field`` names the monotonically increasing record key.
    ``cursor_value`` is the highest value synced so far (ISO-8601 string, or
    ``None`` on a cold start). ``last_synced_at`` records when the last run
    finished, or ``None`` before the first run.
    """

    source_id: str
    cursor_field: str
    cursor_value: str | None
    last_synced_at: str | None

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — курсор как словарь (§20.4)."""
        return {
            "source_id": self.source_id,
            "cursor_field": self.cursor_field,
            "cursor_value": self.cursor_value,
            "last_synced_at": self.last_synced_at,
        }


def filter_new(records: list[dict], cursor: SyncCursor) -> list[dict]:
    """Keep records past the cursor — только новые записи (§20.5).

    Returns the subset of ``records`` whose ``str(record[cursor.cursor_field])``
    is strictly greater than ``cursor.cursor_value`` (lexicographic ISO-8601
    comparison, so the boundary value is excluded). When ``cursor.cursor_value``
    is ``None`` this is a cold start and *all* records are returned. The original
    record dict objects are returned by identity — no copying.
    """
    if cursor.cursor_value is None:
        return list(records)
    boundary = cursor.cursor_value
    return [r for r in records if str(r[cursor.cursor_field]) > boundary]


def advance(records: list[dict], cursor: SyncCursor, last_synced_at: str) -> SyncCursor:
    """Fold a batch into a new cursor — продвинуть курсор на партию (§20.5).

    Returns a *new* frozen cursor whose ``cursor_value`` is the maximum
    ``str(record[cursor.cursor_field])`` over ``records`` (left unchanged when the
    batch is empty, so the watermark never regresses) and whose ``last_synced_at``
    is set to ``last_synced_at``.
    """
    if records:
        new_value: str | None = max(str(r[cursor.cursor_field]) for r in records)
    else:
        new_value = cursor.cursor_value
    return SyncCursor(
        source_id=cursor.source_id,
        cursor_field=cursor.cursor_field,
        cursor_value=new_value,
        last_synced_at=last_synced_at,
    )

"""Backup retention pruning planner — планировщик обрезки бэкапов (§2.7).

Timestamped dumps accumulate in the backup directory; retention keeps only the
recent ones and prunes older ones. This module turns a list of backup filenames
into a deterministic keep/delete plan, without touching the filesystem.

* :func:`parse_backup_name` — parse ``<component>-YYYY-MM-DDThh-mm-ss.<ext>``
  into a :class:`BackupFile`; returns ``None`` when the name does not match.
* :func:`plan_pruning` — keep files whose calendar day is within ``keep_days``
  of ``now_day`` (inclusive boundary), delete strictly-older ones; unparseable
  names are always kept. keep/delete are sorted; ``ok`` is always ``True``.

Everything is a pure function of its inputs and side-effect free.

Public API:

* :class:`BackupFile` — frozen parsed backup with :meth:`BackupFile.as_dict`.
* :class:`RetentionPlan` — frozen plan with :meth:`RetentionPlan.as_dict`.
* :func:`parse_backup_name` — parse a backup filename.
* :func:`plan_pruning` — build a :class:`RetentionPlan`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

__all__ = [
    "BackupFile",
    "RetentionPlan",
    "parse_backup_name",
    "plan_pruning",
]

# <component>-YYYY-MM-DDThh-mm-ss.<ext> — компонент, дата и время дампа.
_NAME_RE = re.compile(
    r"^(?P<component>.+)-"
    r"(?P<day>\d{4}-\d{2}-\d{2})"
    r"T\d{2}-\d{2}-\d{2}"
    r"\.(?P<ext>[^.]+)$"
)


@dataclass(frozen=True, slots=True)
class BackupFile:
    """Parsed backup filename — разобранное имя бэкапа (§2.7).

    ``name`` is the original filename, ``component`` the logical source (e.g.
    ``neo4j``/``pg``), ``day`` the calendar date of the dump as ``YYYY-MM-DD``.
    """

    name: str
    component: str
    day: str

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — бэкап как словарь (§2.7)."""
        return {"name": self.name, "component": self.component, "day": self.day}


@dataclass(frozen=True, slots=True)
class RetentionPlan:
    """Immutable pruning plan — неизменяемый план обрезки (§2.7).

    ``keep`` are the filenames to retain (recent + unparseable), ``delete`` the
    strictly-older ones to prune. Both tuples are sorted; ``ok`` is ``True``.
    """

    keep: tuple[str, ...]
    delete: tuple[str, ...]
    ok: bool

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — план как словарь (§2.7)."""
        return {"keep": list(self.keep), "delete": list(self.delete), "ok": self.ok}


def parse_backup_name(name: str) -> BackupFile | None:
    """Parse ``<component>-YYYY-MM-DDThh-mm-ss.<ext>`` — разобрать имя (§2.7).

    Returns a :class:`BackupFile` on a match, or ``None`` when the filename does
    not follow the timestamped backup convention.
    """
    match = _NAME_RE.match(name)
    if match is None:
        return None
    day = match.group("day")
    try:
        date.fromisoformat(day)
    except ValueError:
        return None
    return BackupFile(name=name, component=match.group("component"), day=day)


def plan_pruning(names: Iterable[str], now_day: str, keep_days: int) -> RetentionPlan:
    """Plan backup pruning — построить план обрезки бэкапов (§2.7).

    A parseable file is **kept** when its calendar day is within ``keep_days``
    of ``now_day`` (inclusive: a file dated exactly ``keep_days`` back is kept),
    and **deleted** when strictly older. Unparseable names are always kept.
    keep/delete are sorted; ``ok`` is always ``True``.
    """
    now = date.fromisoformat(now_day)
    keep: list[str] = []
    delete: list[str] = []
    for name in names:
        parsed = parse_backup_name(name)
        if parsed is None:
            keep.append(name)
            continue
        age_days = (now - date.fromisoformat(parsed.day)).days
        if age_days > keep_days:
            delete.append(name)
        else:
            keep.append(name)
    return RetentionPlan(keep=tuple(sorted(keep)), delete=tuple(sorted(delete)), ok=True)

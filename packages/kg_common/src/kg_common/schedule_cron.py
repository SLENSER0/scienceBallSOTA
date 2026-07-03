"""Cron schedules — расписания cron: next-run и catch-up (§9.5).

A tiny, *pure* cron engine for the scheduler. It answers three questions a
job runner asks, all without ever calling :func:`datetime.now`:

* **When does this fire?**  :func:`matches` — does a given wall-clock minute
  satisfy the spec?
* **When is the next run?** :func:`next_after` — the first matching minute
  *strictly after* a reference instant.
* **What did we miss?**     :func:`missed_ticks` — every matching minute in
  ``(last, now]`` so a scheduler that was asleep can catch up
  («догоняющие запуски») deterministically.

The grammar is the classic five-field crontab: ``minute hour dom month dow``.
Each field supports ``*`` (any), ``a-b`` ranges, ``*/n`` steps (and the usual
``a-b/n`` / ``a/n`` / comma-lists as a convenience). Day-of-week is
``0=Sunday .. 6=Saturday`` with ``7`` accepted as Sunday, matching Vixie cron.

Day matching follows the standard cron quirk: when *both* day-of-month and
day-of-week are restricted (not ``*``), a day matches if *either* field
matches; otherwise both must match («ИЛИ по dom/dow, если оба заданы»).

Everything is a pure function of its inputs — no ambient clock, no I/O — so
the same ``(spec, instant)`` always yields the same answer.

Public API:

* :class:`CronSpec` — frozen, JSON-serialisable parsed schedule.
* :func:`parse_cron` — parse a crontab expression into a :class:`CronSpec`.
* :func:`matches` / :func:`next_after` / :func:`missed_ticks`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

__all__ = [
    "CronSpec",
    "matches",
    "missed_ticks",
    "next_after",
    "parse_cron",
]

# Inclusive (lo, hi) bounds per crontab field — границы полей.
_MINUTE = (0, 59)
_HOUR = (0, 23)
_DOM = (1, 31)
_MONTH = (1, 12)
_DOW = (0, 6)

# Safety cap for the minute-by-minute walk: > 4 years, so an impossible spec
# (e.g. Feb 30) terminates instead of looping forever — предохранитель.
_MAX_MINUTES = 366 * 4 * 24 * 60


@dataclass(frozen=True, slots=True)
class CronSpec:
    """Immutable parsed cron schedule — разобранное расписание (§9.5).

    Each field is the exact set of integers that field may take. ``*`` is
    stored as the field's full inclusive range, so :meth:`as_dict` round-trips
    to sorted lists and callers can detect a restricted field by comparing to
    the full range.
    """

    minute: frozenset[int]
    hour: frozenset[int]
    dom: frozenset[int]
    month: frozenset[int]
    dow: frozenset[int]

    def as_dict(self) -> dict[str, list[int]]:
        """Return sorted lists per field — сериализуемое представление."""
        return {
            "minute": sorted(self.minute),
            "hour": sorted(self.hour),
            "dom": sorted(self.dom),
            "month": sorted(self.month),
            "dow": sorted(self.dow),
        }


def _full(bounds: tuple[int, int]) -> frozenset[int]:
    """Full inclusive range for a field — полный диапазон поля."""
    lo, hi = bounds
    return frozenset(range(lo, hi + 1))


def _parse_field(token: str, bounds: tuple[int, int]) -> frozenset[int]:
    """Parse one crontab field into its integer set — разбор одного поля.

    Supports ``*``, ``a-b``, ``*/n``, ``a-b/n``, ``a/n``, single ints and
    comma-separated lists thereof.
    """
    lo, hi = bounds
    token = token.strip()
    if not token:
        raise ValueError("empty cron field / пустое поле")

    values: set[int] = set()
    for part in token.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            base, _, step_str = part.partition("/")
            step = int(step_str)
            if step <= 0:
                raise ValueError(f"non-positive step / шаг <= 0: {part!r}")
        else:
            base = part

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            start_str, _, end_str = base.partition("-")
            start, end = int(start_str), int(end_str)
        else:
            start = int(base)
            # ``a/n`` walks from ``a`` to the field max; a bare ``a`` is a point.
            end = hi if "/" in part else start

        for value in range(start, end + 1, step):
            if not (lo <= value <= hi):
                raise ValueError(f"value {value} out of range / вне диапазона {bounds}")
            values.add(value)

    if not values:
        raise ValueError(f"cron field yielded no values / поле без значений: {token!r}")
    return frozenset(values)


def parse_cron(expr: str) -> CronSpec:
    """Parse a five-field crontab expression — разбор строки crontab (§9.5).

    ``minute hour day-of-month month day-of-week``. Day-of-week ``7`` is
    normalised to ``0`` (Sunday).
    """
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"expected 5 cron fields, got {len(fields)} / ожидалось 5 полей")

    minute = _parse_field(fields[0], _MINUTE)
    hour = _parse_field(fields[1], _HOUR)
    dom = _parse_field(fields[2], _DOM)
    month = _parse_field(fields[3], _MONTH)
    # Accept 7 as Sunday, then fold it onto 0 — 7 == воскресенье.
    raw_dow = _parse_field(fields[4], (0, 7))
    dow = frozenset(0 if v == 7 else v for v in raw_dow)

    return CronSpec(minute=minute, hour=hour, dom=dom, month=month, dow=dow)


def _cron_dow(dt: datetime) -> int:
    """Cron weekday (0=Sunday) for a datetime — день недели по-крону."""
    # datetime.weekday(): Monday=0 .. Sunday=6 → cron: Sunday=0 .. Saturday=6.
    return (dt.weekday() + 1) % 7


def matches(spec: CronSpec, dt: datetime) -> bool:
    """Does ``dt`` (at minute granularity) satisfy ``spec``? — совпадение."""
    if dt.minute not in spec.minute:
        return False
    if dt.hour not in spec.hour:
        return False
    if dt.month not in spec.month:
        return False

    dom_restricted = spec.dom != _full(_DOM)
    dow_restricted = spec.dow != _full(_DOW)
    dom_hit = dt.day in spec.dom
    dow_hit = _cron_dow(dt) in spec.dow

    if dom_restricted and dow_restricted:
        # Classic cron OR-semantics when both day fields are constrained.
        return dom_hit or dow_hit
    return dom_hit and dow_hit


def next_after(spec: CronSpec, after: datetime) -> datetime:
    """First matching minute strictly after ``after`` — следующий запуск (§9.5)."""
    # Truncate to the minute, then step forward at least one minute so the
    # result is strictly greater than ``after``.
    candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(_MAX_MINUTES):
        if matches(spec, candidate):
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError("no matching time within horizon / нет совпадения в горизонте")


def missed_ticks(spec: CronSpec, last: datetime, now: datetime) -> list[datetime]:
    """Matching minutes in ``(last, now]`` — догоняющие запуски (§9.5).

    Exclusive of ``last`` (already handled), inclusive of ``now``. Returns an
    empty list when ``now <= last``.
    """
    ticks: list[datetime] = []
    tick = next_after(spec, last)
    while tick <= now:
        ticks.append(tick)
        tick = next_after(spec, tick)
    return ticks

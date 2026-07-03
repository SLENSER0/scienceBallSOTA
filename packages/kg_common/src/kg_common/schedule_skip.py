"""Schedule skip logic — логика пропуска тика планировщика (§9.5).

A scheduler that materialises downstream assets does not need to *tick* every
cycle: it only has to run when there is **new** upstream materialisation since
its last successful run. This module is the pure decision core for that gate —
no store, no clock, no side effects.

The scheduler tracks a monotonic *cursor* (the materialisation id of the last
run it processed) and observes the *latest* materialisation currently visible.
From those two integers we decide:

* run — «есть новые материализации»: latest exists and is strictly ahead of the
  cursor (or the cursor is unset);
* skip ``'no_new_materializations'`` — «нет новых»: latest exists but is not
  ahead of the cursor;
* skip ``'no_materializations'`` — «материализаций нет»: nothing to run on yet.

After a run the cursor is advanced with :func:`advance_cursor`, which is
``None``-safe ``max`` of the two values.

Public API:

* :class:`TickDecision` — frozen decision with :meth:`TickDecision.as_dict`.
* :func:`decide_tick`    — decide whether to run this tick.
* :func:`advance_cursor` — compute the next cursor value.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "TickDecision",
    "advance_cursor",
    "decide_tick",
]

#: Allowed reason codes — допустимые коды причин.
_NEW = "new_materializations"
_NO_NEW = "no_new_materializations"
_NONE = "no_materializations"


@dataclass(frozen=True, slots=True)
class TickDecision:
    """Immutable tick decision — неизменяемое решение о тике (§9.5).

    :param run: whether the scheduler should run this tick — запускать ли тик.
    :param reason: one of ``'new_materializations'``, ``'no_new_materializations'``,
        ``'no_materializations'``.
    """

    run: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable mapping — вернуть JSON-совместимый словарь."""
        return {"run": self.run, "reason": self.reason}


def decide_tick(
    *,
    last_run_cursor: int | None,
    latest_materialization: int | None,
) -> TickDecision:
    """Decide whether to run this tick — решить, запускать ли тик (§9.5).

    :param last_run_cursor: materialisation id of the last processed run, or
        ``None`` if the scheduler has never run — курсор прошлого запуска.
    :param latest_materialization: id of the latest visible materialisation, or
        ``None`` if none exists yet — последняя материализация.
    :returns: a :class:`TickDecision`.

    Run when ``latest`` exists and either the cursor is unset or ``latest`` is
    strictly ahead of it. Skip with ``'no_materializations'`` when nothing has
    materialised, or ``'no_new_materializations'`` when ``latest`` is not ahead.
    """
    if latest_materialization is None:
        return TickDecision(run=False, reason=_NONE)
    if last_run_cursor is None or latest_materialization > last_run_cursor:
        return TickDecision(run=True, reason=_NEW)
    return TickDecision(run=False, reason=_NO_NEW)


def advance_cursor(
    last_run_cursor: int | None,
    latest_materialization: int | None,
) -> int | None:
    """Advance the cursor — сдвинуть курсор (``None``-safe ``max``) (§9.5).

    :param last_run_cursor: current cursor, or ``None`` — текущий курсор.
    :param latest_materialization: latest materialisation, or ``None`` — последняя.
    :returns: the greater of the two, or ``None`` when both are ``None``.
    """
    if last_run_cursor is None:
        return latest_materialization
    if latest_materialization is None:
        return last_run_cursor
    return max(last_run_cursor, latest_materialization)

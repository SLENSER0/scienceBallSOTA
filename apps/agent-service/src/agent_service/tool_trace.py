"""§13.23 трассировка вызовов инструментов / tool-call tracing.

Pure-python, deterministic tracing of agent tool invocations. Each traced call is
captured as an immutable :class:`ToolTraceEntry` — what tool ran, with which args,
when it started/finished, whether it succeeded, and a short summary. Timing is
injected via a ``clock`` callable so tests stay deterministic (детерминированные
тесты без реального времени / no wall-clock dependency).

Three helpers:

* :class:`ToolTraceEntry` — frozen record of one tool call with ``duration_ms`` and
  a camelCase :meth:`~ToolTraceEntry.as_dict` projection (``dataRef`` key).
* :func:`traced_tool` — run a tool, time it, and never re-raise (ошибка -> запись со
  status='error' / an error becomes a trace entry, not an exception).
* :func:`append_trace` — immutably append an entry's dict to a trace list.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Status literals for a trace entry (успех / ошибка → ok / error).
_STATUS_OK = "ok"
_STATUS_ERROR = "error"


@dataclass(frozen=True)
class ToolTraceEntry:
    """One traced tool call (§13.23).

    Immutable record of a single tool invocation: ``tool`` name, ``args`` passed,
    ``started_at`` / ``finished_at`` timestamps (from an injected clock), terminal
    ``status`` (``ok`` / ``error``), a human ``summary`` (краткое описание), an
    optional ``data_ref`` pointer to bulky output and an optional ``error`` message.
    """

    tool: str
    args: dict[str, Any]
    started_at: float
    finished_at: float
    status: str
    summary: str
    data_ref: str | None = None
    error: str | None = None

    @property
    def duration_ms(self) -> int:
        """Elapsed time in whole milliseconds (длительность, мс) — never negative."""
        return round((self.finished_at - self.started_at) * 1000)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a camelCase dict (``dataRef`` — не ``data_ref`` / API shape)."""
        return {
            "tool": self.tool,
            "args": self.args,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "summary": self.summary,
            "dataRef": self.data_ref,
            "error": self.error,
        }


def traced_tool(
    name: str,
    fn: Callable[[dict[str, Any]], Any],
    args: dict[str, Any],
    clock: Callable[[], float],
) -> tuple[Any, ToolTraceEntry]:
    """Run ``fn(args)``, timing it via ``clock``, and capture a :class:`ToolTraceEntry`.

    The ``clock`` is read once before and once after the call to stamp
    ``started_at`` / ``finished_at``. On success the entry gets ``status='ok'`` and a
    ``summary`` derived from the result. On any exception the entry gets
    ``status='error'`` with ``error=str(exc)``, the returned result is ``None`` and the
    exception is swallowed (не пробрасывается / never re-raised) — a failing tool is a
    trace record, not a crash. Returns ``(result, entry)``.
    """
    started_at = clock()
    try:
        result = fn(args)
    except Exception as exc:  # a failing tool must not crash the agent / не роняем агента
        finished_at = clock()
        entry = ToolTraceEntry(
            tool=name,
            args=args,
            started_at=started_at,
            finished_at=finished_at,
            status=_STATUS_ERROR,
            summary=f"{name} failed / ошибка инструмента",
            data_ref=None,
            error=str(exc),
        )
        return None, entry
    finished_at = clock()
    entry = ToolTraceEntry(
        tool=name,
        args=args,
        started_at=started_at,
        finished_at=finished_at,
        status=_STATUS_OK,
        summary=f"{name} -> {result!r}",
        data_ref=None,
        error=None,
    )
    return result, entry


def append_trace(trace: list[dict[str, Any]], entry: ToolTraceEntry) -> list[dict[str, Any]]:
    """Return a new trace list with ``entry.as_dict()`` appended (без мутации / immutable).

    The input ``trace`` is not modified — a shallow copy is made, the entry's dict is
    appended to the copy, and the copy is returned (output length == input + 1).
    """
    return [*trace, entry.as_dict()]

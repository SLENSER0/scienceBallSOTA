"""§13.23 наблюдаемость прогона / run observability — metrics aggregator.

Pure-python, deterministic aggregation of a single agent run's telemetry into a
small set of exported metrics (§13.23): tool-call counters, tool-error and
verifier-retry rates, interrupt rate and the share of answers free of
unsupported claims. Nothing here touches wall-clock time, the graph or any
store — a run is summarised straight from its terminal ``state`` dict, so the
numbers are hand-checkable and the tests fully deterministic.

Two layers:

* :func:`compute_run_metrics` folds one run's ``state`` into a frozen
  :class:`RunMetrics` — it counts ``state['tool_trace']`` entries (and those
  with ``status=='error'``), sums their ``duration_ms``, reads
  ``state['verifier_attempts']``, flags a pending ``interrupt_request`` and
  counts verifier-report violations whose ``severity=='unsupported'``.
* :func:`aggregate_runs` rolls a list of :class:`RunMetrics` up into ratio
  metrics (доли/rates as floats) — safe on an empty list (никакого деления на
  ноль / no ZeroDivisionError, all-zero result).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Trace entry status that marks a failed tool call (ошибка вызова инструмента).
_STATUS_ERROR = "error"
# Verifier-violation severity for an unsupported claim (недоказанное утверждение).
_SEVERITY_UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class RunMetrics:
    """Metrics for one agent run (§13.23) / метрики одного прогона.

    ``tool_calls`` is every traced tool invocation, ``tool_errors`` the subset
    that failed (``status=='error'``), ``verifier_attempts`` the retry counter,
    ``interrupt_count`` is 1 iff the run ended awaiting a human interrupt,
    ``unsupported_claims`` counts verifier violations of severity
    ``unsupported`` and ``total_tool_ms`` sums the traced tool durations.
    """

    tool_calls: int
    tool_errors: int
    verifier_attempts: int
    interrupt_count: int
    unsupported_claims: int
    total_tool_ms: float

    def as_dict(self) -> dict[str, float | int]:
        """Serialise every field to a plain dict (round-trips 1:1 / без потерь)."""
        return asdict(self)


def compute_run_metrics(state: dict) -> RunMetrics:
    """Fold a run's terminal ``state`` into a :class:`RunMetrics` (§13.23).

    Reads ``state['tool_trace']`` (a list of entry dicts) for the tool-call
    count, the error count (entries with ``status=='error'``) and the summed
    ``duration_ms``; ``state.get('verifier_attempts', 0)`` verbatim; 1 when
    ``state.get('interrupt_request')`` is truthy else 0; and the number of
    ``state['verifier_report']['violations']`` rows whose ``severity`` equals
    ``unsupported``. Missing keys are treated as empty (безопасно/robust).
    """
    trace = state.get("tool_trace") or []
    tool_calls = len(trace)
    tool_errors = sum(1 for e in trace if e.get("status") == _STATUS_ERROR)
    total_tool_ms = float(sum(e.get("duration_ms", 0) for e in trace))

    verifier_attempts = int(state.get("verifier_attempts", 0))
    interrupt_count = 1 if state.get("interrupt_request") else 0

    report = state.get("verifier_report") or {}
    violations = report.get("violations") or []
    unsupported_claims = sum(1 for v in violations if v.get("severity") == _SEVERITY_UNSUPPORTED)

    return RunMetrics(
        tool_calls=tool_calls,
        tool_errors=tool_errors,
        verifier_attempts=verifier_attempts,
        interrupt_count=interrupt_count,
        unsupported_claims=unsupported_claims,
        total_tool_ms=total_tool_ms,
    )


def aggregate_runs(runs: list[RunMetrics]) -> dict:
    """Roll a list of :class:`RunMetrics` up into ratio metrics / агрегат долей.

    Returns ``{'error_rate', 'retry_rate', 'interrupt_rate', 'unsupported_rate',
    'avg_tool_ms'}`` as floats. ``error_rate`` is errored calls over all tool
    calls; ``retry_rate`` runs that used at least one verifier attempt over all
    runs; ``interrupt_rate`` interrupted runs over all runs; ``unsupported_rate``
    runs with any unsupported claim over all runs; ``avg_tool_ms`` mean tool time
    per call. An empty list yields all-zero floats (без ZeroDivisionError).
    """
    if not runs:
        return {
            "error_rate": 0.0,
            "retry_rate": 0.0,
            "interrupt_rate": 0.0,
            "unsupported_rate": 0.0,
            "avg_tool_ms": 0.0,
        }

    n_runs = len(runs)
    total_calls = sum(r.tool_calls for r in runs)
    total_errors = sum(r.tool_errors for r in runs)
    total_tool_ms = sum(r.total_tool_ms for r in runs)
    retried = sum(1 for r in runs if r.verifier_attempts > 0)
    interrupted = sum(r.interrupt_count for r in runs)
    with_unsupported = sum(1 for r in runs if r.unsupported_claims > 0)

    return {
        "error_rate": (total_errors / total_calls) if total_calls else 0.0,
        "retry_rate": retried / n_runs,
        "interrupt_rate": interrupted / n_runs,
        "unsupported_rate": with_unsupported / n_runs,
        "avg_tool_ms": (total_tool_ms / total_calls) if total_calls else 0.0,
    }

"""Сквозное интеграционное тестирование — pipeline stage-trace assertions (§23.1).

Pure-stdlib validator asserting that an end-to-end run passed through the
expected ordered pipeline stages within a per-stage latency budget. Intended as
a golden-harness helper for cross-service e2e checks, distinct from the
runtime ``retrieval_trace`` / ``tracing`` machinery.

Проверяет, что прогон прошёл ожидаемые стадии конвейера в правильном порядке
и уложился в бюджет задержек по каждой стадии.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class StageEvent:
    """Наблюдённое событие стадии — a single observed pipeline stage span.

    ``start_ms`` / ``end_ms`` are milliseconds on a shared monotonic clock.
    """

    stage: str
    start_ms: float
    end_ms: float

    @property
    def duration_ms(self) -> float:
        """Длительность стадии — wall-clock span of this stage in ms."""
        return self.end_ms - self.start_ms

    def as_dict(self) -> dict[str, float | str]:
        return {
            "stage": self.stage,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True)
class TraceAssertion:
    """Результат проверки трассы — outcome of a trace assertion.

    ``ok`` is True iff no stages are missing, out of order, or over budget.
    """

    ok: bool
    missing_stages: tuple[str, ...]
    out_of_order: tuple[str, ...]
    over_budget: tuple[str, ...]
    total_ms: float

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "missing_stages": list(self.missing_stages),
            "out_of_order": list(self.out_of_order),
            "over_budget": list(self.over_budget),
            "total_ms": self.total_ms,
        }


def check_trace(
    events: Sequence[StageEvent],
    *,
    expected_order: Sequence[str],
    budgets_ms: Mapping[str, float] | None = None,
) -> TraceAssertion:
    """Проверить трассу против ожидаемого порядка стадий и бюджетов.

    - ``missing`` = expected stages that never appear in ``events``.
    - ``out_of_order`` = stages whose first-occurrence index violates the
      relative ordering implied by ``expected_order``.
    - ``over_budget`` = stages whose duration exceeds their configured budget.
    - ``total_ms`` = ``max(end_ms) - min(start_ms)`` over all events (0 if none).

    ``ok`` is True iff all three lists are empty.
    """
    budgets_ms = budgets_ms or {}

    # First-occurrence index of each seen stage, in observed order.
    first_index: dict[str, int] = {}
    for i, ev in enumerate(events):
        if ev.stage not in first_index:
            first_index[ev.stage] = i

    missing = tuple(s for s in expected_order if s not in first_index)

    # Out-of-order: among expected stages that are present, their first
    # occurrences must be strictly increasing in the order given by
    # ``expected_order``. A stage whose first index falls before its
    # predecessor's is flagged.
    out_of_order: list[str] = []
    present_expected = [s for s in expected_order if s in first_index]
    prev_idx = -1
    for stage in present_expected:
        idx = first_index[stage]
        if idx < prev_idx:
            out_of_order.append(stage)
        else:
            prev_idx = idx

    # Over-budget: any event whose duration exceeds its stage budget.
    over: list[str] = []
    seen_over: set[str] = set()
    for ev in events:
        budget = budgets_ms.get(ev.stage)
        if budget is not None and ev.duration_ms > budget and ev.stage not in seen_over:
            over.append(ev.stage)
            seen_over.add(ev.stage)

    if events:
        total_ms = max(ev.end_ms for ev in events) - min(ev.start_ms for ev in events)
    else:
        total_ms = 0.0

    ok = not missing and not out_of_order and not over
    return TraceAssertion(
        ok=ok,
        missing_stages=missing,
        out_of_order=tuple(out_of_order),
        over_budget=tuple(over),
        total_ms=total_ms,
    )

"""Immutable connector sync-metrics counters for observability (§20.13).

Счётчики синхронизации коннекторов — неизменяемые наблюдаемые метрики
(records_synced / records_skipped / merge_auto / merge_review / errors),
отдельные от трассировки в :mod:`kg_common.telemetry`. Immutable counters
for connector sync observability, distinct from OpenTelemetry tracing.

:class:`ConnectorSyncMetrics` — frozen dataclass; :func:`record` возвращает
новый экземпляр с прибавленными значениями (accumulates, original untouched);
:func:`merge` суммирует два набора одной системы; :func:`total_processed`
даёт ``records_synced + records_skipped`` (§20.13).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

__all__ = [
    "ConnectorSyncMetrics",
    "merge",
    "record",
    "total_processed",
]


@dataclass(frozen=True)
class ConnectorSyncMetrics:
    """Снимок счётчиков синхронизации одного коннектора (§20.13).

    A frozen snapshot of one connector's sync counters. Поля неизменяемы;
    обновления производятся через :func:`record` / :func:`merge`, которые
    возвращают новый экземпляр (original untouched).
    """

    system: str
    records_synced: int = 0
    records_skipped: int = 0
    merge_auto: int = 0
    merge_review: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int | str]:
        """Систему и пять счётчиков как обычный ``dict`` (6 ключей)."""
        return {
            "system": self.system,
            "records_synced": self.records_synced,
            "records_skipped": self.records_skipped,
            "merge_auto": self.merge_auto,
            "merge_review": self.merge_review,
            "errors": self.errors,
        }


def record(
    m: ConnectorSyncMetrics,
    *,
    synced: int = 0,
    skipped: int = 0,
    merge_auto: int = 0,
    merge_review: int = 0,
    errors: int = 0,
) -> ConnectorSyncMetrics:
    """Прибавить значения к каждому полю, вернуть новый frozen (accumulates).

    Add the given deltas to each counter and return a new frozen instance;
    ``m`` остаётся неизменным (original immutable).
    """
    return replace(
        m,
        records_synced=m.records_synced + synced,
        records_skipped=m.records_skipped + skipped,
        merge_auto=m.merge_auto + merge_auto,
        merge_review=m.merge_review + merge_review,
        errors=m.errors + errors,
    )


def merge(a: ConnectorSyncMetrics, b: ConnectorSyncMetrics) -> ConnectorSyncMetrics:
    """Просуммировать все счётчики двух наборов одной системы (§20.13).

    Sum every counter of ``a`` and ``b``. Оба должны относиться к одной
    системе; иначе :class:`ValueError` (mismatched ``system``).
    """
    if a.system != b.system:
        raise ValueError(f"system mismatch: {a.system!r} != {b.system!r}")
    return ConnectorSyncMetrics(
        system=a.system,
        records_synced=a.records_synced + b.records_synced,
        records_skipped=a.records_skipped + b.records_skipped,
        merge_auto=a.merge_auto + b.merge_auto,
        merge_review=a.merge_review + b.merge_review,
        errors=a.errors + b.errors,
    )


def total_processed(m: ConnectorSyncMetrics) -> int:
    """``records_synced + records_skipped`` — total records seen (§20.13)."""
    return m.records_synced + m.records_skipped

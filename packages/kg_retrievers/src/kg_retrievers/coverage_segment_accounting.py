"""Coverage-denominator reconciliation against parser-reported segment totals (§25.5).

RU: Сверка знаменателя покрытия. Здесь мы сопоставляем ``total_segments`` —
основную истину (ground truth) от парсера о числе сегментов в контексте — с
``seen_segments``, реально залогированными телеметрией покрытия. Расхождение
``total - seen`` выявляет *недологирование* (unlogged): сегменты, которые парсер
видел, но телеметрия покрытия не зафиксировала. Дополнительно ловятся невозможные
аномалии: ``seen > total`` (залогировано больше, чем всего есть) и
``emitted > seen`` (эмитировано фактов больше, чем виденных сегментов). Этот
модуль намеренно ОТЛИЧАЕТСЯ от :mod:`coverage_yield_report` и
:mod:`coverage_report`, которые никогда не сверяются с истинным числом сегментов.

EN: Coverage-denominator reconciliation. We compare ``total_segments`` — the
parser-reported ground truth for how many segments a context contains — against
``seen_segments`` actually recorded by coverage telemetry. The gap
``total - seen`` surfaces *under-logging* (unlogged segments): segments the
parser saw that telemetry never recorded. We additionally flag impossible
anomalies: ``seen > total`` (more logged than exist) and ``emitted > seen``
(more facts emitted than segments seen). This module is deliberately DISTINCT
from :mod:`coverage_yield_report` and :mod:`coverage_report`, neither of which
reconciles against a total-segment ground truth.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

_SEEN_EXCEEDS_TOTAL = "seen_exceeds_total"
_EMITTED_EXCEEDS_SEEN = "emitted_exceeds_seen"


@dataclass(frozen=True)
class AccountingRow:
    """Per-context reconciliation row (§25.5).

    RU: Строка сверки для одного контекста: недологированные сегменты, доля
    покрытия и код аномалии.
    EN: Reconciliation row for one context: unlogged segments, coverage ratio
    and an anomaly code.
    """

    context_key: str
    total: int
    seen: int
    emitted: int
    unlogged: int
    coverage_ratio: float
    anomaly: str

    def as_dict(self) -> dict[str, object]:
        """RU: Сериализация строки. EN: Serialise the row to a plain dict."""
        return {
            "context_key": self.context_key,
            "total": self.total,
            "seen": self.seen,
            "emitted": self.emitted,
            "unlogged": self.unlogged,
            "coverage_ratio": self.coverage_ratio,
            "anomaly": self.anomaly,
        }


@dataclass(frozen=True)
class AccountingReport:
    """Aggregate reconciliation report (§25.5).

    RU: Сводный отчёт сверки: строки, суммарное недологирование и число аномалий.
    EN: Aggregate reconciliation report: rows, total under-logging and anomaly
    count.
    """

    rows: list[AccountingRow]
    total_unlogged: int
    n_anomalies: int

    def as_dict(self) -> dict[str, object]:
        """RU: Сериализация отчёта. EN: Serialise the report to a plain dict."""
        return {
            "rows": [r.as_dict() for r in self.rows],
            "total_unlogged": self.total_unlogged,
            "n_anomalies": self.n_anomalies,
        }


def _classify(total: int, seen: int, emitted: int) -> str:
    """RU: Определить код аномалии для строки. EN: Determine a row's anomaly code."""
    if seen > total:
        return _SEEN_EXCEEDS_TOTAL
    if emitted > seen:
        return _EMITTED_EXCEEDS_SEEN
    return ""


def _build_row(row: Mapping[str, object]) -> AccountingRow:
    """RU: Построить строку сверки из dict. EN: Build one reconciliation row."""
    context_key = str(row["context_key"])
    total = int(row["total_segments"])
    seen = int(row["seen_segments"])
    emitted = int(row["emitted_facts"])
    unlogged = max(total - seen, 0)
    coverage_ratio = seen / total if total > 0 else 0.0
    anomaly = _classify(total, seen, emitted)
    return AccountingRow(
        context_key=context_key,
        total=total,
        seen=seen,
        emitted=emitted,
        unlogged=unlogged,
        coverage_ratio=coverage_ratio,
        anomaly=anomaly,
    )


def reconcile_coverage(rows: Iterable[Mapping[str, object]]) -> AccountingReport:
    """Reconcile parser totals against logged seen-segments (§25.5).

    RU: Для каждого контекста считаем недологированные сегменты и код аномалии,
    затем агрегируем суммарное недологирование и число аномалий.
    EN: For each context compute unlogged segments and an anomaly code, then
    aggregate total under-logging and the anomaly count.
    """
    built = [_build_row(r) for r in rows]
    total_unlogged = sum(r.unlogged for r in built)
    n_anomalies = sum(1 for r in built if r.anomaly)
    return AccountingReport(
        rows=built,
        total_unlogged=total_unlogged,
        n_anomalies=n_anomalies,
    )

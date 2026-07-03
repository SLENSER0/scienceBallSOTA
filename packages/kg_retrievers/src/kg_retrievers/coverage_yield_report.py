"""Observed-yield coverage report over coverage telemetry (§25.5/§25.10).

RU: Отчёт о наблюдаемой отдаче (observed yield) экстракторов по строкам
:class:`kg_common.storage.CoverageStats`. Здесь *наблюдаемая отдача* — это
чисто эмпирическая доля попыток, давших хотя бы одну находку
(``n_found / n_attempts``), и она намеренно держится ОТДЕЛЬНО от *recall prior*
(§25.10): recall prior — это оценочный/байесовский приор полноты экстрактора,
используемый слоем уверенности-в-отсутствии (§25.11), тогда как observed yield
не делает никаких вероятностных допущений и просто описывает то, что реально
наблюдалось в телеметрии покрытия.

EN: Report of extractor *observed yield* over :class:`CoverageStats` rows. The
observed yield is the purely empirical fraction of attempts that produced at
least one find (``n_found / n_attempts``); it is deliberately kept DISTINCT from
the *recall prior* (§25.10) consumed by the confidence-of-absence layer
(§25.11). A *blind spot* is a target type that was attempted at least once yet
never yielded anything (``n_attempts > 0 and n_found == 0``).
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common.storage import CoverageStats


@dataclass(frozen=True)
class YieldRow:
    """Per-target-type observed-yield row (§25.5).

    RU: Строка наблюдаемой отдачи для одного ``target_type``.
    EN: Observed-yield row for a single ``target_type``.
    """

    target_type: str
    seen: int
    emitted: int
    observed_yield: float
    blind_spot: bool

    def as_dict(self) -> dict[str, object]:
        """RU: Сериализация строки. EN: Serialise the row to a plain dict."""
        return {
            "target_type": self.target_type,
            "seen": self.seen,
            "emitted": self.emitted,
            "observed_yield": self.observed_yield,
            "blind_spot": self.blind_spot,
        }


@dataclass(frozen=True)
class CoverageYieldReport:
    """Aggregate observed-yield report (§25.5/§25.10).

    RU: Сводный отчёт о наблюдаемой отдаче по всем ``target_type``.
    EN: Aggregate observed-yield report across all target types.
    """

    rows: list[YieldRow]
    total_seen: int
    total_emitted: int
    overall_yield: float
    blind_spots: list[str]

    def as_dict(self) -> dict[str, object]:
        """RU: Сериализация отчёта. EN: Serialise the report to a plain dict."""
        return {
            "rows": [r.as_dict() for r in self.rows],
            "total_seen": self.total_seen,
            "total_emitted": self.total_emitted,
            "overall_yield": self.overall_yield,
            "blind_spots": list(self.blind_spots),
        }


def build_yield_report(stats: list[CoverageStats]) -> CoverageYieldReport:
    """Build an observed-yield report from coverage stats (§25.5/§25.10).

    RU: Для каждой строки статистики ``seen = n_attempts``,
    ``emitted = n_found``, ``observed_yield = n_found / n_attempts`` (``0.0``
    при ``n_attempts == 0``); ``blind_spot`` истинно, когда попытки были, но
    находок нет. Общая отдача — ``total_emitted / total_seen``.

    EN: For each stat ``seen = n_attempts``, ``emitted = n_found``, observed
    yield ``= n_found / n_attempts`` (``0.0`` when ``n_attempts == 0``);
    ``blind_spot`` is true when there were attempts but no finds. Overall yield
    is ``total_emitted / total_seen`` (``0.0`` when nothing was seen). Rows are
    sorted by ``target_type``; ``blind_spots`` is the sorted list of flagged
    target types.
    """
    rows: list[YieldRow] = []
    for stat in sorted(stats, key=lambda s: s.target_type):
        seen = stat.n_attempts
        emitted = stat.n_found
        observed_yield = emitted / seen if seen else 0.0
        blind_spot = seen > 0 and emitted == 0
        rows.append(
            YieldRow(
                target_type=stat.target_type,
                seen=seen,
                emitted=emitted,
                observed_yield=observed_yield,
                blind_spot=blind_spot,
            )
        )

    total_seen = sum(r.seen for r in rows)
    total_emitted = sum(r.emitted for r in rows)
    overall_yield = total_emitted / total_seen if total_seen else 0.0
    blind_spots = sorted(r.target_type for r in rows if r.blind_spot)

    return CoverageYieldReport(
        rows=rows,
        total_seen=total_seen,
        total_emitted=total_emitted,
        overall_yield=overall_yield,
        blind_spots=blind_spots,
    )

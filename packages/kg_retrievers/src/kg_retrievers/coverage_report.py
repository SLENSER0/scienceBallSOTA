"""Raw seen/emitted coverage aggregation by modality with observed yield (§25.5).

Where :mod:`kg_retrievers.recall_report` summarises *derived* recall priors and
:mod:`kg_retrievers.coverage_dashboard` counts *graph nodes*, this module works
straight off the raw coverage telemetry denominators/numerators. It rolls the
per-(extractor × target_type) rows of :class:`kg_common.storage.base.CoverageStats`
up **by modality** (способ извлечения — prose / table_row / catalog_row), keeping
the honest denominator: a modality that was *seen* many segments yet *emitted*
zero facts is a real blind spot (слепая зона), reported with ``observed_yield ==
0.0`` — never silently dropped.

Per modality we track:

- ``seen_segments``  — сколько сегментов просмотрено (Σ ``n_attempts``);
- ``emitted_facts``  — сколько фактов извлечено (Σ ``n_found``);
- ``observed_yield`` — наблюдаемый выход = emitted / seen, ``0.0`` when seen is 0.

Input rows may be :class:`CoverageStats` objects **or** equivalent plain dicts
(``target_type`` / ``n_attempts`` / ``n_found``); rows sharing a ``target_type``
are summed. Pure Python and read-only: reads no store and writes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _observed_yield(emitted: int, seen: int) -> float:
    """Наблюдаемый выход emitted / seen; ``0.0`` when ``seen`` is 0 (no divide-by-zero)."""
    return emitted / seen if seen else 0.0


def _row_field(row: Any, name: str, default: Any) -> Any:
    """Read ``name`` from a dict row or a :class:`CoverageStats`-like object."""
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


@dataclass(frozen=True)
class ModalityCoverage:
    """Seen/emitted coverage for one modality with its observed yield (§25.5)."""

    modality: str
    seen_segments: int
    emitted_facts: int
    observed_yield: float

    def as_dict(self) -> dict:
        return {
            "modality": self.modality,
            "seen_segments": self.seen_segments,
            "emitted_facts": self.emitted_facts,
            "observed_yield": self.observed_yield,
        }


@dataclass(frozen=True)
class CoverageReport:
    """Raw coverage rolled up by modality with an overall observed yield (§25.5)."""

    by_modality: dict[str, ModalityCoverage]
    total_seen: int
    total_emitted: int
    overall_yield: float

    def as_dict(self) -> dict:
        return {
            "by_modality": {k: v.as_dict() for k, v in self.by_modality.items()},
            "total_seen": self.total_seen,
            "total_emitted": self.total_emitted,
            "overall_yield": self.overall_yield,
        }


def aggregate_coverage(stats: list) -> CoverageReport:
    """Aggregate raw coverage telemetry by modality (§25.5).

    Accepts :class:`kg_common.storage.base.CoverageStats` objects — using
    ``n_attempts`` as ``seen_segments`` and ``n_found`` as ``emitted_facts`` —
    or equivalent dicts. Rows that share a ``target_type`` are summed. A modality
    seen but never emitting stays visible with ``observed_yield == 0.0`` (честная
    слепая зона, not dropped). An empty input yields ``overall_yield == 0.0``.
    """
    seen_by: dict[str, int] = {}
    emitted_by: dict[str, int] = {}
    order: list[str] = []
    for row in stats:
        modality = str(_row_field(row, "target_type", ""))
        seen = int(_row_field(row, "n_attempts", 0))
        emitted = int(_row_field(row, "n_found", 0))
        if modality not in seen_by:
            order.append(modality)
            seen_by[modality] = 0
            emitted_by[modality] = 0
        seen_by[modality] += seen
        emitted_by[modality] += emitted

    by_modality: dict[str, ModalityCoverage] = {}
    for modality in order:
        seen = seen_by[modality]
        emitted = emitted_by[modality]
        by_modality[modality] = ModalityCoverage(
            modality=modality,
            seen_segments=seen,
            emitted_facts=emitted,
            observed_yield=_observed_yield(emitted, seen),
        )

    total_seen = sum(seen_by.values())
    total_emitted = sum(emitted_by.values())
    return CoverageReport(
        by_modality=by_modality,
        total_seen=total_seen,
        total_emitted=total_emitted,
        overall_yield=_observed_yield(total_emitted, total_seen),
    )

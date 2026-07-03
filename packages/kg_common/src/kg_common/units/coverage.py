"""Unit-coverage report over a measurement population — покрытие единицами (§7.12).

Answers a curator's data-quality question: of all the measurements in a
population, how many actually carry a unit of measurement, and how are those
units distributed? A high *missing-unit ratio* signals that the extractor or the
source is dropping units and the numbers are not safely comparable (§7.2/§7.7).

Pure python — no store, no I/O. A *measurement* is anything from which a unit can
be read: a :class:`~collections.abc.Mapping` with a ``"unit"`` key, or an object
with a ``.unit`` attribute. A unit counts as **present** only when it is a
non-empty string after stripping; ``None``, ``""`` and whitespace all count as
*missing*. Histogram keys are the reported unit strings (stripped, verbatim —
``"HV"`` and ``"hv"`` are distinct); no folding is applied here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class UnitCoverage:
    """Unit-coverage summary over a measurement population (§7.12).

    Invariant: ``total == with_unit + without_unit`` and
    ``sum(by_unit.values()) == with_unit``.
    """

    total: int
    with_unit: int
    without_unit: int
    by_unit: dict[str, int] = field(default_factory=dict)
    missing_unit_ratio: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready mapping; ``by_unit`` is copied so the frozen value is safe."""
        return {
            "total": self.total,
            "with_unit": self.with_unit,
            "without_unit": self.without_unit,
            "by_unit": dict(self.by_unit),
            "missing_unit_ratio": self.missing_unit_ratio,
        }


def _measurement_unit(measurement: Any) -> str | None:
    """Read the unit token from *measurement*; ``None`` if absent/blank.

    Accepts a mapping (``measurement["unit"]``) or an attribute-bearing object
    (``measurement.unit``). Anything that is ``None`` or blank after stripping is
    treated as *no unit* (единица измерения отсутствует).
    """
    if isinstance(measurement, Mapping):
        raw = measurement.get("unit")
    else:
        raw = getattr(measurement, "unit", None)
    if raw is None:
        return None
    token = str(raw).strip()
    return token or None


def unit_coverage(measurements: Iterable[Any]) -> UnitCoverage:
    """Summarize unit presence over *measurements* (§7.12).

    Iterates the population once, counting how many measurements carry a unit,
    building the per-unit histogram, and computing the missing-unit ratio
    (``without_unit / total``, ``0.0`` for an empty population). The histogram is
    ordered by descending count then unit string for a stable, hand-checkable
    report. ``missing_unit_ratio`` always lies in ``[0.0, 1.0]``.
    """
    total = 0
    without_unit = 0
    counts: dict[str, int] = {}
    for measurement in measurements:
        total += 1
        unit = _measurement_unit(measurement)
        if unit is None:
            without_unit += 1
        else:
            counts[unit] = counts.get(unit, 0) + 1

    with_unit = total - without_unit
    by_unit = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    missing_unit_ratio = without_unit / total if total else 0.0
    return UnitCoverage(
        total=total,
        with_unit=with_unit,
        without_unit=without_unit,
        by_unit=by_unit,
        missing_unit_ratio=missing_unit_ratio,
    )

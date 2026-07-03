"""Reference conversion-table self-check harness — таблица сверки (§7.8).

§7.8 of the specification lists a small **reference conversion table**: a set of
hand-checkable rows (``180 °C → 453.15 K`` and friends) that the family of
per-dimension converters must reproduce. The table lives in the doc, but nothing
in code exercises the *live* converters against it — so a silent regression in
any single converter (temperature, stress, corrosion, cooling, hardness…) could
drift from the documented figures unnoticed.

This module closes that gap. It encodes the §7.8 rows as frozen
:class:`ReferenceCase` records (:data:`REFERENCE_CASES`) and provides
:func:`run_reference_table`, which dispatches each case — by its ``dimension``
tag — to the appropriate converter and reports ``{case, got, ok}``:

* ``temperature`` / ``length`` → :func:`conversions.convert`;
* ``time``      → :func:`time_duration.to_seconds` / :func:`~.to_hours`;
* ``stress``    → :func:`stress_strength.to_mpa`;
* ``corrosion`` → :func:`corrosion_rate.convert_corrosion_rate`;
* ``cooling``   → :func:`cooling_rate.convert_cooling_rate`;
* ``hardness``  → :func:`hardness.convert_hardness`.

RU: Каждая строка проверяется живым конвертером с заданным допуском.
EN: Every row is checked against its live converter within a stated tolerance.

Pure Python, no I/O. Import this module and assert ``all(r["ok"] …)`` in tests
or a startup self-check to guarantee the converters still honour the doc.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common.units.conversions import convert
from kg_common.units.cooling_rate import convert_cooling_rate
from kg_common.units.corrosion_rate import convert_corrosion_rate
from kg_common.units.hardness import convert_hardness
from kg_common.units.stress_strength import to_mpa
from kg_common.units.time_duration import to_hours, to_seconds

# ---------------------------------------------------------------------------
# Dimension tags (§7.8) — pick which live converter handles a row.
# ---------------------------------------------------------------------------
TEMPERATURE = "temperature"
LENGTH = "length"
TIME = "time"
STRESS = "stress"
CORROSION = "corrosion"
COOLING = "cooling"
HARDNESS = "hardness"

#: Every dimension the harness knows how to dispatch (§7.8).
DIMENSIONS: tuple[str, ...] = (
    TEMPERATURE,
    LENGTH,
    TIME,
    STRESS,
    CORROSION,
    COOLING,
    HARDNESS,
)


@dataclass(frozen=True)
class ReferenceCase:
    """One §7.8 reference-table row — строка эталонной таблицы (§7.8).

    A hand-checkable conversion the live converters must reproduce: convert
    ``from_value`` on ``from_unit`` to ``to_unit`` and land within ``tolerance``
    (absolute) of ``expected``. ``dimension`` selects the converter used by
    :func:`run_reference_table`.
    """

    from_value: float
    from_unit: str
    to_unit: str
    expected: float
    tolerance: float
    dimension: str

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view of the row — представление строки (§7.8)."""
        return {
            "from_value": self.from_value,
            "from_unit": self.from_unit,
            "to_unit": self.to_unit,
            "expected": self.expected,
            "tolerance": self.tolerance,
            "dimension": self.dimension,
        }


# ---------------------------------------------------------------------------
# §7.8 — the reference conversion table, as hand-verified doc rows. Tolerances
# are absolute; hardness carries a wide band (±10 HV) as the ASTM E140 steel
# cross-scale mapping is only approximate.
# ---------------------------------------------------------------------------
REFERENCE_CASES: tuple[ReferenceCase, ...] = (
    ReferenceCase(180.0, "degC", "K", 453.15, 1e-6, TEMPERATURE),
    ReferenceCase(100.0, "degC", "degF", 212.0, 1e-6, TEMPERATURE),
    ReferenceCase(1.0, "ksi", "MPa", 6.894757, 1e-4, STRESS),
    ReferenceCase(1.0, "GPa", "MPa", 1000.0, 1e-6, STRESS),
    ReferenceCase(2.0, "h", "s", 7200.0, 1e-6, TIME),
    ReferenceCase(90.0, "min", "h", 1.5, 1e-9, TIME),
    ReferenceCase(1.0, "mpy", "mm/year", 0.0254, 1e-6, CORROSION),
    ReferenceCase(60.0, "degC/min", "K/s", 1.0, 1e-9, COOLING),
    ReferenceCase(1000.0, "nm", "um", 1.0, 1e-9, LENGTH),
    ReferenceCase(30.0, "HRC", "HV", 302.0, 10.0, HARDNESS),
)


class UnknownReferenceDimensionError(ValueError):
    """Case carries a dimension the harness cannot dispatch — (§7.8)."""

    def __init__(self, dimension: str) -> None:
        self.dimension = dimension
        super().__init__(f"unknown reference dimension: {dimension!r}")


def _dispatch(case: ReferenceCase) -> float:
    """Route *case* to its live converter and return the numeric result (§7.8).

    RU: Диспетчеризация по размерности. EN: dispatch by ``case.dimension`` to
    the matching converter, raising for an unknown tag.
    """
    if case.dimension in (TEMPERATURE, LENGTH):
        return convert(case.from_value, case.from_unit, case.to_unit)
    if case.dimension == TIME:
        if case.to_unit == "s":
            return to_seconds(case.from_value, case.from_unit)
        if case.to_unit == "h":
            return to_hours(case.from_value, case.from_unit)
        raise UnknownReferenceDimensionError(f"{case.dimension}:{case.to_unit}")
    if case.dimension == STRESS:
        return to_mpa(case.from_value, case.from_unit)
    if case.dimension == CORROSION:
        return convert_corrosion_rate(case.from_value, case.from_unit, case.to_unit).value
    if case.dimension == COOLING:
        return convert_cooling_rate(case.from_value, case.from_unit, case.to_unit).value
    if case.dimension == HARDNESS:
        return convert_hardness(case.from_value, case.from_unit, case.to_unit).value
    raise UnknownReferenceDimensionError(case.dimension)


def run_reference_table() -> list[dict[str, object]]:
    """Check every §7.8 row against its live converter — сверка таблицы (§7.8).

    Returns one report per :data:`REFERENCE_CASES` entry, each a mapping
    ``{"case": <as_dict>, "got": <float>, "ok": <bool>}`` where ``ok`` is true
    iff ``abs(got − expected) <= tolerance``.
    """
    reports: list[dict[str, object]] = []
    for case in REFERENCE_CASES:
        got = _dispatch(case)
        ok = abs(got - case.expected) <= case.tolerance
        reports.append({"case": case.as_dict(), "got": got, "ok": ok})
    return reports

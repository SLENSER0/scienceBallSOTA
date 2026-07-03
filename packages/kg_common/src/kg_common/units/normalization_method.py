"""``normalization_method`` semantics — direct | converted | rule | manual (§7.5).

§7.5 defines four values a normalized measurement's ``normalization_method`` may
take, but no module derives them and
``measurement_normalizer.NormalizedMeasurement`` never records one. This module
closes that gap: given a measurement's *raw* unit and its *canonical* unit (plus
a few flags), :func:`classify_normalization_method` decides which of the four
labels applies and returns a :class:`MethodDecision`.

Способ нормализации — the four semantics:

* ``manual``    — a человек fixed the value/unit by hand; overrides everything.
* ``rule``      — the canonical value came from a rule / assumption / conversion
  formula rather than a plain unit swap (``rule_based`` or ``assumed``), *or* a
  unit was missing so a default had to be assumed.
* ``direct``    — raw and canonical unit are the same (case-insensitively); the
  value passed through unchanged (``HV`` → ``HV``, ``hv`` → ``HV``).
* ``converted`` — raw and canonical units are both present and differ, so a unit
  conversion was applied (``ksi`` → ``MPa``).

Pure stdlib — no dependency on the numeric normalizer; callers pass the two unit
strings they already hold.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: The four legal ``normalization_method`` labels (§7.5).
METHODS: frozenset[str] = frozenset({"direct", "converted", "rule", "manual"})


@dataclass(frozen=True)
class MethodDecision:
    """A resolved ``normalization_method`` and why it was chosen (§7.5).

    ``method`` — one of :data:`METHODS`. ``canonical_unit`` — the canonical unit
    the value is expressed in (``None`` when unknown). ``reason`` — a short,
    hand-readable justification (RU/EN) for the chosen ``method``.
    """

    method: str
    canonical_unit: str | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready mapping of the three fields."""
        return {
            "method": self.method,
            "canonical_unit": self.canonical_unit,
            "reason": self.reason,
        }


def _norm(unit: str | None) -> str | None:
    """Strip + case-fold a unit for comparison; ``None``/blank → ``None``."""
    if unit is None:
        return None
    stripped = unit.strip()
    return stripped.casefold() if stripped else None


def classify_normalization_method(
    raw_unit: str | None,
    canonical_unit: str | None,
    *,
    manual: bool = False,
    assumed: bool = False,
    rule_based: bool = False,
) -> MethodDecision:
    """Derive the §7.5 ``normalization_method`` for one measurement.

    Правила разрешения (in strict priority order):

    1. ``manual`` — a human override wins first, regardless of units.
    2. ``rule``   — ``rule_based`` or ``assumed`` conversion (formula/default).
    3. ``direct`` — raw and canonical units match, case-insensitively.
    4. ``converted`` — both units present and differ.
    5. ``rule``   — a unit is missing (nothing to compare), so a default was
       assumed.

    ``canonical_unit`` on the result is the *given* ``canonical_unit`` argument
    unchanged (callers already resolved it); only ``method``/``reason`` are
    derived here.
    """
    if manual:
        return MethodDecision("manual", canonical_unit, "manual override — задано вручную")

    if rule_based or assumed:
        return MethodDecision(
            "rule",
            canonical_unit,
            "rule/assumption applied — правило или допущение",
        )

    raw_cf = _norm(raw_unit)
    can_cf = _norm(canonical_unit)

    if raw_cf is not None and can_cf is not None:
        if raw_cf == can_cf:
            return MethodDecision(
                "direct",
                canonical_unit,
                "raw unit == canonical — прямое значение без пересчёта",
            )
        return MethodDecision(
            "converted",
            canonical_unit,
            "unit conversion applied — единицы отличаются, выполнен пересчёт",
        )

    return MethodDecision(
        "rule",
        canonical_unit,
        "unit missing — единица отсутствует, применено допущение",
    )

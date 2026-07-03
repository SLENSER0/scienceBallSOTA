"""Canonical registry of §24.13 comparison parameters (Сравнительные параметры).

The MCDA and comparison-matrix layers (``mcda_scoring``, ``comparison_matrices``)
score alternatives against a fixed set of *criteria* but historically assumed the
caller supplied each criterion's *orientation* (benefit vs. cost) and unit. This
module is the single source of truth for that metadata: each §24.13 parameter is
registered once as a frozen :class:`ComparisonCriterion` carrying its human label
(RU), benefit/cost direction, physical unit, and thematic group.

Read-only, in-memory registry — no graph access. ``benefit=True`` means *higher is
better* (recovery, efficiency); ``benefit=False`` means *lower is better* (capex,
opex, energy consumption). Каждый критерий учтён ровно один раз.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComparisonCriterion:
    """One canonical §24.13 comparison parameter (Сравнительный параметр).

    ``key`` is a lowercase snake_case identifier shared with MCDA weight/direction
    maps. ``label_ru`` is the Russian display label. ``benefit`` is the orientation:
    True when a larger value is better (benefit), False when smaller is better
    (cost). ``unit`` is the physical unit or ``None`` for dimensionless/qualitative
    parameters. ``group`` is the thematic grouping (e.g. ``"economics"``).
    """

    key: str
    label_ru: str
    benefit: bool
    unit: str | None
    group: str

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label_ru": self.label_ru,
            "benefit": self.benefit,
            "unit": self.unit,
            "group": self.group,
        }


def _c(key: str, label_ru: str, benefit: bool, unit: str | None, group: str) -> ComparisonCriterion:
    """Construct a :class:`ComparisonCriterion` (internal registry helper)."""
    return ComparisonCriterion(key=key, label_ru=label_ru, benefit=benefit, unit=unit, group=group)


# ---------------------------------------------------------------------------
# Canonical registry — §24.13 Сравнительные параметры.
# Orientation: benefit=True → higher is better; benefit=False → lower is better.
# ---------------------------------------------------------------------------
CRITERIA: dict[str, ComparisonCriterion] = {
    "efficiency": _c("efficiency", "Эффективность", True, "%", "performance"),
    "recovery": _c("recovery", "Извлечение", True, "%", "performance"),
    "removal_efficiency": _c("removal_efficiency", "Степень очистки", True, "%", "performance"),
    "capex": _c("capex", "Капитальные затраты", False, "руб.", "economics"),
    "opex": _c("opex", "Эксплуатационные затраты", False, "руб./год", "economics"),
    "energy_consumption": _c(
        "energy_consumption", "Энергопотребление", False, "кВт·ч/т", "economics"
    ),
    "cold_climate_applicability": _c(
        "cold_climate_applicability", "Применимость в холодном климате", True, None, "applicability"
    ),
    "environmental_constraints": _c(
        "environmental_constraints", "Экологические ограничения", False, None, "environment"
    ),
    "maturity_level": _c("maturity_level", "Уровень зрелости технологии", True, "TRL", "readiness"),
    "domestic_availability": _c(
        "domestic_availability", "Отечественная доступность", True, None, "readiness"
    ),
}


def get_criterion(key: str) -> ComparisonCriterion:
    """Return the registered criterion for ``key`` (raises ``KeyError`` if unknown)."""
    return CRITERIA[key]


def is_benefit(key: str) -> bool:
    """True iff ``key`` is a benefit criterion — higher is better (raises on unknown)."""
    return CRITERIA[key].benefit


def criteria_for_group(group: str) -> tuple[ComparisonCriterion, ...]:
    """Return all criteria in ``group``, sorted by key (empty tuple if none match)."""
    matches = [c for c in CRITERIA.values() if c.group == group]
    return tuple(sorted(matches, key=lambda c: c.key))

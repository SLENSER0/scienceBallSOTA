"""Dimensional consistency checks for property measurements (§7.15).

Builds on the canonical unit registry (:mod:`kg_common.units.registry`) to answer
two questions ingest/curation code repeatedly asks:

* :func:`same_dimension` — do two units share a physical **dimension**? So that a
  value in ``MPa`` and one in ``bar`` are recognized as comparable (both
  *pressure*), while ``MPa`` vs ``HV`` (hardness) are flagged as incomparable.
* :func:`check_property_unit` — is a unit **dimensionally** right for a property?
  ``prop:tensile_strength`` expects a pressure unit, ``prop:temperature`` a
  temperature unit, ``prop:hardness`` a hardness scale.

Размерности берутся из реестра единиц; шкалы твёрдости (HV/HB/HRC) не входят в
реестр (they carry no SI factor — see :mod:`kg_common.units.hardness`), so they
are resolved here to a dedicated pseudo-dimension :data:`HARDNESS`.

Pure Python, no I/O and no ``pint`` dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common.units.registry import UNIT_REGISTRY, resolve_alias

# ---------------------------------------------------------------------------
# §7.15 — hardness pseudo-dimension. HV/HB/HRC are ordinal steel scales, not SI
# units, so they are absent from the registry; treat them as one dimension so a
# hardness property accepts any hardness scale but rejects a pressure unit.
# ---------------------------------------------------------------------------
HARDNESS = "hardness"

_HARDNESS_UNITS: frozenset[str] = frozenset({"hv", "hb", "hrc"})

# Canonical property_id → expected physical dimension (§7.15). Dimension strings
# mirror :data:`kg_common.units.registry.DIMENSIONS` plus :data:`HARDNESS`.
_PROPERTY_DIMENSION: dict[str, str] = {
    "prop:hardness": HARDNESS,
    "prop:tensile_strength": "pressure",
    "prop:temperature": "temperature",
}

# Short spellings → canonical property_id — удобные псевдонимы (§7.15).
_PROPERTY_ALIASES: dict[str, str] = {
    "hardness": "prop:hardness",
    "tensile": "prop:tensile_strength",
    "tensile_strength": "prop:tensile_strength",
    "temperature": "prop:temperature",
}


def _fold_property(property_id: str | None) -> str | None:
    """Resolve *property_id* (alias or ``prop:*``) to a canonical id (§7.15)."""
    if property_id is None:
        return None
    key = str(property_id).strip().lower()
    if key in _PROPERTY_DIMENSION:
        return key
    return _PROPERTY_ALIASES.get(key)


def dimension_for_unit(unit: str | None) -> str | None:
    """Physical dimension of *unit*, or ``None`` if unregistered (§7.15).

    Resolves RU/EN aliases via the registry first (``"МПа"`` → pressure); falls
    back to the hardness scales (``HV``/``HB``/``HRC`` → :data:`HARDNESS`) that
    the registry does not carry. Never raises — размерность неизвестна ⇒ ``None``.
    """
    canonical = resolve_alias(unit)
    if canonical is not None:
        return UNIT_REGISTRY[canonical].dimension
    if unit is None:
        return None
    if str(unit).strip().lower() in _HARDNESS_UNITS:
        return HARDNESS
    return None


def dimension_for_property(property_id: str | None) -> str | None:
    """Expected physical dimension for *property_id*, or ``None`` if unknown (§7.15)."""
    canonical = _fold_property(property_id)
    if canonical is None:
        return None
    return _PROPERTY_DIMENSION[canonical]


def same_dimension(u1: str | None, u2: str | None) -> bool:
    """True iff *u1* and *u2* share a known physical dimension (§7.15).

    Symmetric. Both units must resolve to the *same* non-``None`` dimension:
    ``same_dimension("MPa", "bar")`` is ``True`` (both pressure),
    ``same_dimension("MPa", "HV")`` is ``False``, and any unregistered unit
    (``"banana"``) yields ``False`` — размерности несопоставимы.
    """
    d1 = dimension_for_unit(u1)
    d2 = dimension_for_unit(u2)
    return d1 is not None and d1 == d2


@dataclass(frozen=True)
class DimensionCheck:
    """Result of :func:`check_property_unit` — проверка размерности (§7.15).

    ``ok``                 — unit is dimensionally valid for the property.
    ``expected_dimension`` — dimension the property requires (``None`` if the
                             property is unknown).
    ``actual_dimension``   — dimension of the supplied unit (``None`` if the unit
                             is unregistered).
    ``property_id`` / ``unit`` — the inputs, echoed back for traceability.
    ``reason``             — RU/EN-neutral human-readable explanation.
    """

    property_id: str
    unit: str | None
    ok: bool
    expected_dimension: str | None
    actual_dimension: str | None
    reason: str

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — результат проверки (§7.15)."""
        return {
            "property_id": self.property_id,
            "unit": self.unit,
            "ok": self.ok,
            "expected_dimension": self.expected_dimension,
            "actual_dimension": self.actual_dimension,
            "reason": self.reason,
        }


def check_property_unit(property_id: str, unit: str | None) -> DimensionCheck:
    """Check that *unit* is dimensionally right for *property_id* (§7.15).

    Handles ``prop:hardness`` (hardness scale), ``prop:tensile_strength``
    (pressure) and ``prop:temperature`` (temperature); short names
    (``"hardness"``, ``"tensile"``, ``"temperature"``) resolve too.

    * unknown property → ``ok=False``, ``expected_dimension=None``;
    * unregistered unit → ``ok=False``, ``actual_dimension=None``;
    * dimension mismatch → ``ok=False`` with both dimensions populated;
    * match → ``ok=True``.
    """
    expected = dimension_for_property(property_id)
    if expected is None:
        return DimensionCheck(
            property_id,
            unit,
            False,
            None,
            dimension_for_unit(unit),
            f"unknown property {property_id!r}",
        )
    actual = dimension_for_unit(unit)
    if actual is None:
        return DimensionCheck(
            property_id,
            unit,
            False,
            expected,
            None,
            f"unknown unit {unit!r} for {property_id}",
        )
    if actual != expected:
        return DimensionCheck(
            property_id,
            unit,
            False,
            expected,
            actual,
            f"unit {unit!r} is {actual}, but {property_id} expects {expected}",
        )
    return DimensionCheck(
        property_id,
        unit,
        True,
        expected,
        actual,
        f"unit {unit!r} matches expected dimension {expected}",
    )


__all__ = [
    "HARDNESS",
    "DimensionCheck",
    "check_property_unit",
    "dimension_for_property",
    "dimension_for_unit",
    "same_dimension",
]

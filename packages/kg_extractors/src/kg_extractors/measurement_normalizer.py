"""Measurement normalizer → NormalizedMeasurement (§7.5).

Bridges the raw unit zoo (:mod:`kg_extractors.units`) and the property-unit
policy (:mod:`kg_common.units.policy`) into one gated result. Given a value +
raw unit (and, optionally, a canonical ``property_id``) it:

* canonicalizes the unit + value via :func:`kg_extractors.units.to_canonical`
  (нормализация единиц — ``А/м2`` → ``A/m^2``, ``мА/см2`` → ``A/m^2`` …);
* checks the unit is allowed for the property (§7.2, ``is_unit_allowed``);
* checks the value against the physical range (§7.7, ``validate_range``);
* raises curator flags — ``out_of_range`` (вне диапазона),
  ``unit_not_allowed`` (недопустимая единица), ``missing_unit`` (нет единицы) —
  and derives ``review_needed`` (нужна проверка) from them.

Unknown properties stay graceful: units are still normalized, no policy flag is
raised (the policy simply cannot judge them). Units that pint cannot convert
(e.g. Vickers ``HV``) fall back to the raw value, whose policy bounds are stated
in that same canonical unit, so the range check remains meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kg_common.units.policy import (
    PROPERTY_UNIT_POLICY,
    is_unit_allowed,
    validate_range,
)
from kg_extractors.units import to_canonical

# Curator flag tokens (§7.5).
FLAG_OUT_OF_RANGE = "out_of_range"
FLAG_UNIT_NOT_ALLOWED = "unit_not_allowed"
FLAG_MISSING_UNIT = "missing_unit"


@dataclass(frozen=True)
class NormalizedMeasurement:
    """One gated, canonicalized measurement (§7.5).

    Fields
    ------
    property_id
        Canonical ``prop:*`` id the value describes, or ``None`` if unknown.
    value_raw
        The value exactly as supplied (int/float/str — исходное значение).
    value
        ``value_raw`` coerced to ``float`` (``None`` if non-numeric).
    unit
        The raw unit token as supplied (``None`` / empty ⇒ missing).
    value_normalized
        Value in the canonical unit; falls back to ``value`` when the unit is
        not pint-convertible (нормализованное значение).
    normalized_unit
        Canonical unit string (``A/m^2`` …); falls back to ``unit``.
    in_range
        ``True`` unless the value is outside the property's hard physical
        bounds (в диапазоне).
    flags
        Raised curator flags (``out_of_range`` / ``unit_not_allowed`` /
        ``missing_unit``).
    review_needed
        ``True`` iff any flag was raised (нужна ручная проверка).
    """

    value_raw: object
    value: float | None
    unit: str | None
    value_normalized: float | None
    normalized_unit: str | None
    in_range: bool
    flags: list[str] = field(default_factory=list)
    review_needed: bool = False
    property_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Full structured view (all fields, including ``None``)."""
        return {
            "property_id": self.property_id,
            "value_raw": self.value_raw,
            "value": self.value,
            "unit": self.unit,
            "value_normalized": self.value_normalized,
            "normalized_unit": self.normalized_unit,
            "in_range": self.in_range,
            "flags": list(self.flags),
            "review_needed": self.review_needed,
        }

    def to_neo4j_props(self) -> dict[str, object]:
        """DB columns for a ``:Measurement`` node (§7.5).

        Neo4j stores only primitives / arrays of primitives and drops ``null``
        properties, so ``None`` values are omitted; ``flags`` is always a
        (possibly empty) list of strings.
        """
        props: dict[str, object] = {
            "value_raw": self.value_raw,
            "in_range": self.in_range,
            "flags": list(self.flags),
            "review_needed": self.review_needed,
        }
        if self.property_id is not None:
            props["property_id"] = self.property_id
        if self.value is not None:
            props["value"] = self.value
        if self.unit is not None:
            props["unit"] = self.unit
        if self.value_normalized is not None:
            props["value_normalized"] = self.value_normalized
        if self.normalized_unit is not None:
            props["normalized_unit"] = self.normalized_unit
        return props


def _to_float(value: object) -> float | None:
    """Coerce *value* to ``float`` (comma decimals allowed); ``None`` on failure."""
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _unit_missing(unit: str | None) -> bool:
    return unit is None or not str(unit).strip()


def normalize_measurement(
    value: object,
    unit: str | None,
    *,
    property_id: str | None = None,
) -> NormalizedMeasurement:
    """Normalize + gate one measurement into a :class:`NormalizedMeasurement` (§7.5).

    Canonicalizes ``value``/``unit`` via :func:`kg_extractors.units.to_canonical`,
    then — when *property_id* names a known property — checks the unit policy
    (§7.2) and physical range (§7.7), raising flags and setting
    ``review_needed`` accordingly. Unknown properties are judged gracefully: the
    units are still normalized and no policy flag is raised.
    """
    numeric = _to_float(value)
    missing = _unit_missing(unit)
    unit_str = None if missing else str(unit)

    # --- unit + value canonicalization (нормализация единиц) ----------------
    norm = None
    if not missing and numeric is not None:
        norm = to_canonical(numeric, unit_str)
    if norm is not None:
        value_normalized: float | None = norm.value
        normalized_unit: str | None = norm.unit
    else:
        # not pint-convertible (e.g. HV) — keep the raw value/unit as canonical.
        value_normalized = numeric
        normalized_unit = unit_str

    flags: list[str] = []
    in_range = True
    known = property_id is not None and property_id in PROPERTY_UNIT_POLICY

    # --- единицы измерения: policy gate (§7.2) ------------------------------
    if missing:
        # A unitless property (e.g. pH) legitimately accepts "no unit".
        if not (known and is_unit_allowed(property_id, unit)):
            flags.append(FLAG_MISSING_UNIT)
    elif known and not is_unit_allowed(property_id, unit):
        flags.append(FLAG_UNIT_NOT_ALLOWED)

    # --- физический диапазон: range gate (§7.7) -----------------------------
    if property_id is not None and value_normalized is not None:
        result = validate_range(property_id, value_normalized)
        if result.severity == "error":
            flags.append(FLAG_OUT_OF_RANGE)
            in_range = False

    return NormalizedMeasurement(
        property_id=property_id,
        value_raw=value,
        value=numeric,
        unit=unit_str,
        value_normalized=value_normalized,
        normalized_unit=normalized_unit,
        in_range=in_range,
        flags=flags,
        review_needed=bool(flags),
    )

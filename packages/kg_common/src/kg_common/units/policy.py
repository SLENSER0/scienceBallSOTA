"""Property-unit policy + physical-range validation (§7.2 / §7.7).

Defines :data:`PROPERTY_UNIT_POLICY` — for each canonical ``property_id`` the
allowed measurement units, the canonical unit, and the physical/typical value
bounds — and the helpers that gate a measurement against it:

* :func:`allowed_units` / :func:`is_unit_allowed` / :func:`unit_ok_for` —
  единицы измерения: which units may carry a given property (§7.2).
* :func:`validate_range` — физический диапазон: flag values that are physically
  impossible (severity ``"error"``) or suspicious outliers (``"warning"``)
  relative to the canonical-unit bounds (§7.7).

Canonical ``prop:*`` ids mirror ``kg_extractors.property_extractor.PROPERTY_VOCAB``
and the ER controlled vocabulary (``kg_er.store.property_vocab``); canonical unit
strings follow ``kg_extractors.units`` (``A/m^2``, ``m/s``, ``mg/L``, ``V``).
Pure python — no ``pint`` dependency.
"""

from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass

# ---------------------------------------------------------------------------
# §7.2 — property → unit policy + §7.7 physical / typical value bounds.
#
# ``allowed_units``  : units a measurement of this property may legitimately use.
# ``canonical_unit`` : the unit range bounds below are expressed in ("" = unitless).
# ``min`` / ``max``  : hard physical bounds — outside ⇒ severity "error".
# ``typical_min/max``: (optional) plausible operating band — inside hard bounds
#                      but outside this band ⇒ severity "warning" (outlier).
# ---------------------------------------------------------------------------
PROPERTY_UNIT_POLICY: dict[str, dict[str, object]] = {
    # metallurgy — твёрдость (Vickers/Brinell/Rockwell-C), bounds in HV.
    "prop:hardness": {
        "allowed_units": ("HV", "HB", "HRC"),
        "canonical_unit": "HV",
        "min": 0.0,
        "max": 2000.0,
        "typical_min": 20.0,
        "typical_max": 1200.0,
    },
    # предел прочности — tensile strength, bounds in MPa.
    "prop:tensile_strength": {
        "allowed_units": ("MPa", "GPa", "N/mm2", "kgf/mm2"),
        "canonical_unit": "MPa",
        "min": 0.0,
        "max": 6000.0,
        "typical_min": 50.0,
        "typical_max": 4000.0,
    },
    # плотность тока — current density, bounds in A/m^2.
    "prop:current_density": {
        "allowed_units": ("A/m^2", "mA/cm^2"),
        "canonical_unit": "A/m^2",
        "min": 0.0,
        "max": 100000.0,
        "typical_min": 1.0,
        "typical_max": 20000.0,
    },
    # скорость потока — flow velocity, bounds in m/s.
    "prop:flow_velocity": {
        "allowed_units": ("m/s", "cm/s"),
        "canonical_unit": "m/s",
        "min": 0.0,
        "max": 100.0,
        "typical_min": 0.001,
        "typical_max": 30.0,
    },
    # извлечение — recovery, percent (0..100 by definition).
    "prop:recovery": {
        "allowed_units": ("%", "percent"),
        "canonical_unit": "%",
        "min": 0.0,
        "max": 100.0,
    },
    # степень очистки — removal efficiency, percent (0..100 by definition).
    "prop:removal_efficiency": {
        "allowed_units": ("%", "percent"),
        "canonical_unit": "%",
        "min": 0.0,
        "max": 100.0,
    },
    # минерализация — total dissolved solids, bounds in mg/L.
    "prop:tds": {
        "allowed_units": ("mg/L", "g/L"),
        "canonical_unit": "mg/L",
        "min": 0.0,
        "max": 500000.0,
        "typical_min": 0.0,
        "typical_max": 100000.0,
    },
    # температура — temperature, bounds in °C (min = absolute zero).
    "prop:temperature": {
        "allowed_units": ("C", "degC", "K"),
        "canonical_unit": "C",
        "min": -273.15,
        "max": 6000.0,
        "typical_min": -50.0,
        "typical_max": 2000.0,
    },
    # pH — dimensionless / unitless, 0..14.
    "prop:ph": {
        "allowed_units": (),
        "canonical_unit": "",
        "min": 0.0,
        "max": 14.0,
    },
    # напряжение — voltage, bounds in V.
    "prop:voltage": {
        "allowed_units": ("V", "mV", "kV"),
        "canonical_unit": "V",
        "min": 0.0,
        "max": 100000.0,
        "typical_min": 0.0,
        "typical_max": 2000.0,
    },
}

# tokens that denote "no unit" for a unitless property (e.g. pH).
_UNITLESS_TOKENS = frozenset({"", "1", "unitless", "dimensionless", "none", "-"})


def _norm_unit(unit: str | None) -> str:
    """Fold a unit token for comparison: NFKC, drop ``^``/spaces, lowercase.

    So ``A/m^2``, ``A/m2`` and ``A/m²`` collapse to one key, and ``HV``/``hv``
    match. NFKC maps superscripts (``²`` → ``2``) to their ASCII form.
    """
    if unit is None:
        return ""
    u = unicodedata.normalize("NFKC", str(unit)).strip()
    return u.replace("^", "").replace(" ", "").lower()


@dataclass(frozen=True)
class UnitCheck:
    """Result of :func:`unit_ok_for` (§7.2)."""

    ok: bool
    reason: str
    severity: str  # "ok" | "error" | "unknown"
    canonical_unit: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RangeResult:
    """Result of :func:`validate_range` (§7.7)."""

    ok: bool
    reason: str
    severity: str  # "ok" | "warning" | "error" | "unknown"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def allowed_units(property_id: str) -> tuple[str, ...]:
    """Return the tuple of allowed unit strings for *property_id* (§7.2).

    Empty tuple for an unknown property or for a unitless property (e.g. pH).
    """
    spec = PROPERTY_UNIT_POLICY.get(property_id)
    if spec is None:
        return ()
    return tuple(spec["allowed_units"])  # type: ignore[arg-type]


def is_unit_allowed(property_id: str, unit: str | None) -> bool:
    """True iff *unit* is permitted for *property_id* (§7.2), case/format-folded.

    Unknown property → ``False``. A unitless property (pH) accepts only the
    unitless tokens (``None``, ``""``, ``"unitless"`` …).
    """
    spec = PROPERTY_UNIT_POLICY.get(property_id)
    if spec is None:
        return False
    units: tuple[str, ...] = tuple(spec["allowed_units"])  # type: ignore[arg-type]
    if not units:  # unitless property
        return _norm_unit(unit) in _UNITLESS_TOKENS
    allowed = {_norm_unit(u) for u in units}
    return _norm_unit(unit) in allowed


def unit_ok_for(property_id: str, unit: str | None) -> UnitCheck:
    """Structured unit check for *property_id* / *unit* (§7.2).

    Unknown property is graceful: ``ok=True`` with severity ``"unknown"`` (the
    policy cannot judge it) rather than an error.
    """
    spec = PROPERTY_UNIT_POLICY.get(property_id)
    if spec is None:
        return UnitCheck(True, f"no unit policy for {property_id!r}", "unknown")
    canonical = str(spec["canonical_unit"])
    if is_unit_allowed(property_id, unit):
        return UnitCheck(True, "unit allowed", "ok", canonical or None)
    units: tuple[str, ...] = tuple(spec["allowed_units"])  # type: ignore[arg-type]
    shown = ", ".join(units) if units else "(unitless)"
    reason = f"unit {unit!r} not allowed for {property_id}; allowed: {shown}"
    return UnitCheck(False, reason, "error", canonical or None)


def validate_range(property_id: str, value: float) -> RangeResult:
    """Validate *value* against the physical range for *property_id* (§7.7).

    Returns a :class:`RangeResult` whose ``severity`` is:

    * ``"error"``   — outside the hard physical bounds (``ok=False``), e.g.
      hardness 100000 HV or a percentage above 100.
    * ``"warning"`` — physically possible but outside the typical band
      (``ok=True``) — an outlier worth a curator's glance.
    * ``"ok"``      — within the typical (or hard) range.
    * ``"unknown"`` — no policy for this property (``ok=True``, graceful).

    Bounds are interpreted in the property's ``canonical_unit``.
    """
    spec = PROPERTY_UNIT_POLICY.get(property_id)
    if spec is None:
        return RangeResult(True, f"no unit policy for {property_id!r}", "unknown")
    if value is None or isinstance(value, bool):
        return RangeResult(False, f"value is not numeric: {value!r}", "error")
    try:
        v = float(value)
    except (TypeError, ValueError):
        return RangeResult(False, f"value is not numeric: {value!r}", "error")

    unit = str(spec["canonical_unit"]) or "(unitless)"
    lo = spec.get("min")
    hi = spec.get("max")
    if lo is not None and v < float(lo):  # type: ignore[arg-type]
        return RangeResult(False, f"{v:g} below physical minimum {float(lo):g} {unit}", "error")
    if hi is not None and v > float(hi):  # type: ignore[arg-type]
        return RangeResult(False, f"{v:g} above physical maximum {float(hi):g} {unit}", "error")

    tlo = spec.get("typical_min")
    thi = spec.get("typical_max")
    if tlo is not None and v < float(tlo):  # type: ignore[arg-type]
        return RangeResult(
            True, f"{v:g} below typical minimum {float(tlo):g} {unit} (outlier)", "warning"
        )
    if thi is not None and v > float(thi):  # type: ignore[arg-type]
        return RangeResult(
            True, f"{v:g} above typical maximum {float(thi):g} {unit} (outlier)", "warning"
        )
    return RangeResult(True, f"{v:g} {unit} within range", "ok")

"""Extended unit-conversion registry — конвертация единиц измерения (§7.10).

Complements the property-unit *policy* (:mod:`kg_common.units.policy`, which
decides *which* unit a property may carry) with the arithmetic that actually
converts a number between units of the **same physical dimension**:

* temperature — ``°C`` / ``K`` / ``°F`` (affine, non-zero offset);
* pressure    — ``MPa`` / ``bar`` / ``atm`` / ``psi`` / ``kPa``;
* energy      — ``J`` / ``kJ`` / ``cal`` / ``kcal`` / ``eV``;
* length      — ``m`` / ``mm`` / ``µm`` / ``nm``;
* fraction    — ``%`` / ``ppm`` / ``fraction``.

Each unit is described by a frozen :class:`UnitSpec` mapping a value to its
dimension's *base unit* by an affine transform ``base = value·scale + offset``
(``offset == 0`` for every dimension except temperature). Conversion is then
«к базе и обратно»: :func:`convert` sends the source value to the shared base
unit and back out through the target unit.

Public API:

* :data:`CONVERSIONS`      — the registry, ``symbol → UnitSpec``.
* :func:`convert`          — value from one unit to another (same dimension).
* :func:`dimension_of`     — physical dimension of a unit (raises if unknown).
* :func:`are_compatible`   — do two units share a dimension (never raises).
* :class:`IncompatibleUnitsError` — raised by :func:`convert` across dimensions.

Pure Python, no I/O and no ``pint`` dependency. Unit strings are matched after
NFKC folding, so the micro sign ``µ`` (U+00B5) and Greek ``μ`` (U+03BC) — and a
handful of ASCII aliases (``C``/``degC``, ``F``/``degF``, ``um``) — all resolve.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Dimension families (§7.10) and their shared base unit (the unit whose
# ``scale == 1`` / ``offset == 0``; every conversion routes through it).
# ---------------------------------------------------------------------------
TEMPERATURE = "temperature"
PRESSURE = "pressure"
ENERGY = "energy"
LENGTH = "length"
FRACTION = "fraction"

DIMENSIONS: tuple[str, ...] = (TEMPERATURE, PRESSURE, ENERGY, LENGTH, FRACTION)

BASE_UNITS: dict[str, str] = {
    TEMPERATURE: "K",
    PRESSURE: "kPa",
    ENERGY: "J",
    LENGTH: "nm",
    FRACTION: "ppm",
}

# Fahrenheit ↔ Kelvin offset: K = °F·(5/9) + (273.15 − 32·5/9).
_F_SCALE = 5.0 / 9.0
_F_OFFSET = 273.15 - 32.0 * 5.0 / 9.0


class UnknownUnitError(ValueError):
    """Unit symbol is not in the registry — неизвестная единица (§7.10)."""

    def __init__(self, unit: str) -> None:
        self.unit = unit
        super().__init__(f"unknown unit: {unit!r}")


class IncompatibleUnitsError(ValueError):
    """Units belong to different dimensions — несовместимые размерности (§7.10).

    Raised by :func:`convert` when asked to cross dimension families (e.g.
    temperature → pressure), which is physically meaningless.
    """

    def __init__(self, from_unit: str, to_unit: str, from_dim: str, to_dim: str) -> None:
        self.from_unit = from_unit
        self.to_unit = to_unit
        self.from_dim = from_dim
        self.to_dim = to_dim
        super().__init__(
            f"cannot convert {from_unit!r} ({from_dim}) to {to_unit!r} ({to_dim}): "
            "different dimensions"
        )


@dataclass(frozen=True)
class UnitSpec:
    """Immutable conversion spec for one unit — единица измерения (§7.10).

    A value on this unit maps to the dimension's base unit by the affine
    transform ``base = value·scale + offset`` and back by
    ``value = (base − offset) / scale``. Linear dimensions (pressure, energy,
    length, fraction) use ``offset == 0``; only temperature (``°C``/``°F`` ↔
    ``K``) needs a non-zero offset.
    """

    symbol: str
    dimension: str
    scale: float
    offset: float = 0.0

    def to_base(self, value: float) -> float:
        """Value on this unit → the dimension's base unit."""
        return value * self.scale + self.offset

    def from_base(self, base: float) -> float:
        """Value on the dimension's base unit → this unit."""
        return (base - self.offset) / self.scale

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — строка таблицы конвертации (§7.10)."""
        return {
            "symbol": self.symbol,
            "dimension": self.dimension,
            "scale": self.scale,
            "offset": self.offset,
        }


# ---------------------------------------------------------------------------
# §7.10 — the conversion registry. Base units chosen so intra-dimension factors
# stay integral where possible (kPa/J/nm/ppm), keeping round numbers exact.
# ---------------------------------------------------------------------------
CONVERSIONS: dict[str, UnitSpec] = {
    # temperature — base K, affine (non-zero offset).
    "K": UnitSpec("K", TEMPERATURE, 1.0, 0.0),
    "°C": UnitSpec("°C", TEMPERATURE, 1.0, 273.15),
    "°F": UnitSpec("°F", TEMPERATURE, _F_SCALE, _F_OFFSET),
    # pressure — base kPa.
    "kPa": UnitSpec("kPa", PRESSURE, 1.0),
    "MPa": UnitSpec("MPa", PRESSURE, 1000.0),
    "bar": UnitSpec("bar", PRESSURE, 100.0),
    "atm": UnitSpec("atm", PRESSURE, 101.325),
    "psi": UnitSpec("psi", PRESSURE, 6.894757293168361),
    # energy — base J (thermochemical calorie: 1 cal = 4.184 J).
    "J": UnitSpec("J", ENERGY, 1.0),
    "kJ": UnitSpec("kJ", ENERGY, 1000.0),
    "cal": UnitSpec("cal", ENERGY, 4.184),
    "kcal": UnitSpec("kcal", ENERGY, 4184.0),
    "eV": UnitSpec("eV", ENERGY, 1.602176634e-19),
    # length — base nm.
    "nm": UnitSpec("nm", LENGTH, 1.0),
    "µm": UnitSpec("µm", LENGTH, 1000.0),
    "mm": UnitSpec("mm", LENGTH, 1_000_000.0),
    "m": UnitSpec("m", LENGTH, 1_000_000_000.0),
    # fraction — base ppm (dimensionless ratio family).
    "ppm": UnitSpec("ppm", FRACTION, 1.0),
    "%": UnitSpec("%", FRACTION, 10_000.0),
    "fraction": UnitSpec("fraction", FRACTION, 1_000_000.0),
}

# Human/OCR aliases → canonical symbol. Keys are matched after NFKC folding, so
# ``µm`` and ``μm`` already coincide; ``um`` is a pure-ASCII fallback.
_ALIASES: dict[str, tuple[str, ...]] = {
    "°C": ("C", "degC", "celsius"),
    "K": ("kelvin",),
    "°F": ("F", "degF", "fahrenheit"),
    "µm": ("um", "micron", "microns"),
    "%": ("percent", "pct"),
    "fraction": ("frac", "ratio"),
}


def _normalize(unit: str) -> str:
    """Fold a unit token for lookup: NFKC + strip, case preserved (§7.10).

    Case is significant for units (``MPa`` ≠ ``mPa``, ``K`` ≠ ``k``), so unlike
    the policy normalizer this deliberately does **not** lowercase.
    """
    return unicodedata.normalize("NFKC", str(unit)).strip()


def _build_lookup() -> dict[str, str]:
    """Normalized symbol/alias → canonical symbol — таблица поиска (§7.10)."""
    lookup: dict[str, str] = {}
    for symbol in CONVERSIONS:
        lookup[_normalize(symbol)] = symbol
    for canonical, aliases in _ALIASES.items():
        for alias in aliases:
            lookup[_normalize(alias)] = canonical
    return lookup


_LOOKUP: dict[str, str] = _build_lookup()


def _try_spec(unit: str) -> UnitSpec | None:
    """Resolve *unit* to its :class:`UnitSpec`, or ``None`` if unknown."""
    canonical = _LOOKUP.get(_normalize(unit))
    if canonical is None:
        return None
    return CONVERSIONS[canonical]


def _spec(unit: str) -> UnitSpec:
    """Resolve *unit* to its :class:`UnitSpec`, raising if unknown."""
    spec = _try_spec(unit)
    if spec is None:
        raise UnknownUnitError(unit)
    return spec


def is_known_unit(unit: str) -> bool:
    """True iff *unit* (after folding/aliasing) is in the registry (§7.10)."""
    return _try_spec(unit) is not None


def dimension_of(unit: str) -> str:
    """Return the physical dimension of *unit* (§7.10).

    Raises :class:`UnknownUnitError` for an unregistered unit.
    """
    return _spec(unit).dimension


def are_compatible(u1: str, u2: str) -> bool:
    """True iff *u1* and *u2* share a dimension and are convertible (§7.10).

    A predicate — never raises: an unknown unit simply yields ``False``.
    """
    s1 = _try_spec(u1)
    s2 = _try_spec(u2)
    return s1 is not None and s2 is not None and s1.dimension == s2.dimension


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert *value* from *from_unit* to *to_unit* (same dimension, §7.10).

    Routes через базовую единицу измерения: ``value`` → base → target. Raises
    :class:`UnknownUnitError` for an unregistered unit and
    :class:`IncompatibleUnitsError` when the units belong to different
    dimensions (e.g. temperature → pressure).
    """
    src = _spec(from_unit)
    dst = _spec(to_unit)
    if src.dimension != dst.dimension:
        raise IncompatibleUnitsError(from_unit, to_unit, src.dimension, dst.dimension)
    return dst.from_base(src.to_base(float(value)))

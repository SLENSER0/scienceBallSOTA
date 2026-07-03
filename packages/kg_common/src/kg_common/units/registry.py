"""Canonical unit registry with dimensions + RU/EN aliases (§7.11).

A single source of truth mapping every *canonical* unit string to its physical
**dimension**, its **SI multiplicative factor**, and the human/OCR **aliases**
(both кириллица and Latin) that should resolve to it. Complements the
property-unit *policy* (:mod:`kg_common.units.policy`) and the conversion
*arithmetic* (:mod:`kg_common.units.conversions`) with a small, hashable
catalogue that ingest/curation code can share and version.

Covers five families used across mining & metallurgy:

* pressure          — ``Pa`` / ``kPa`` / ``MPa`` / ``bar`` / ``atm`` (base ``Pa``);
* temperature       — ``degC`` / ``K`` (base ``K``, affine — see note below);
* length            — ``m`` / ``mm`` / ``cm`` / ``um`` / ``nm`` (base ``m``);
* mass-fraction     — ``%`` / ``ppm`` / ``ppb`` (base = dimensionless fraction);
* current-density   — ``A/m^2`` / ``mA/cm^2`` (base ``A/m^2``).

Public API:

* :data:`UNIT_REGISTRY`   — ``canonical → UnitDef`` (frozen, ``as_dict()``).
* :func:`resolve_alias`   — RU/EN alias → canonical unit, or ``None``.
* :func:`dimension_of`    — physical dimension of a (possibly aliased) unit.
* :func:`registry_version`— stable content hash of the whole registry.

Aliases are matched after NFKC folding — единицы измерения normalized так, что
the micro sign ``µ`` (U+00B5) ≡ Greek ``μ`` (U+03BC), the superscript ``²`` ≡
``2``, ``^`` and spaces are dropped, and case is folded — so ``МПа``/``mpa``,
``А/м²``/``a/m^2`` and ``µm``/``мкм`` all land on one canonical.

Note on temperature: ``degC`` ↔ ``K`` is *affine* (non-zero offset). This
registry records only the multiplicative ``si_factor`` (``1.0`` for both); the
offset is applied by :func:`kg_common.units.conversions.convert`, not here.

Pure Python, no I/O and no ``pint`` dependency.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# §7.11 — dimension families and their SI base unit (the unit whose
# ``si_factor == 1.0``; every ``si_factor`` scales a value onto that base).
# ---------------------------------------------------------------------------
PRESSURE = "pressure"
TEMPERATURE = "temperature"
LENGTH = "length"
MASS_FRACTION = "mass_fraction"
CURRENT_DENSITY = "current_density"

DIMENSIONS: tuple[str, ...] = (PRESSURE, TEMPERATURE, LENGTH, MASS_FRACTION, CURRENT_DENSITY)

SI_BASE_UNIT: dict[str, str] = {
    PRESSURE: "Pa",
    TEMPERATURE: "K",
    LENGTH: "m",
    MASS_FRACTION: "%",  # base ratio == 1; % carries si_factor 0.01
    CURRENT_DENSITY: "A/m^2",
}


@dataclass(frozen=True)
class UnitDef:
    """Immutable registry entry for one canonical unit — единица измерения (§7.11).

    ``canonical``  — the canonical unit string this entry defines.
    ``dimension``  — one of :data:`DIMENSIONS` (физическая размерность).
    ``aliases``    — RU/EN/OCR spellings that resolve to ``canonical`` (NFKC-folded
                     at lookup time); the canonical itself is always resolvable and
                     is *not* repeated here.
    ``si_factor``  — multiply a value in this unit by ``si_factor`` to express it in
                     the dimension's SI base unit (linear only; temperature offset is
                     applied elsewhere — see module docstring).
    """

    canonical: str
    dimension: str
    aliases: tuple[str, ...]
    si_factor: float

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — строка каталога единиц (§7.11)."""
        return {
            "canonical": self.canonical,
            "dimension": self.dimension,
            "aliases": list(self.aliases),
            "si_factor": self.si_factor,
        }


# ---------------------------------------------------------------------------
# §7.11 — the registry. Canonical strings mirror ``kg_extractors.units`` (degC,
# A/m^2, …) so extractor output and this catalogue speak the same vocabulary.
# ---------------------------------------------------------------------------
UNIT_REGISTRY: dict[str, UnitDef] = {
    # pressure — давление, base Pa.
    "Pa": UnitDef("Pa", PRESSURE, ("Па", "па", "pascal"), 1.0),
    "kPa": UnitDef("kPa", PRESSURE, ("кПа", "кпа", "kpa"), 1_000.0),
    "MPa": UnitDef("MPa", PRESSURE, ("МПа", "мпа", "mpa", "N/mm^2", "Н/мм2"), 1_000_000.0),
    "bar": UnitDef("bar", PRESSURE, ("бар",), 100_000.0),
    "atm": UnitDef("atm", PRESSURE, ("атм", "atmosphere"), 101_325.0),
    # temperature — температура, base K (affine: si_factor is the scale only).
    "degC": UnitDef("degC", TEMPERATURE, ("°C", "C", "°С", "celsius", "град.C"), 1.0),
    "K": UnitDef("K", TEMPERATURE, ("К", "kelvin"), 1.0),
    # length — длина, base m.
    "m": UnitDef("m", LENGTH, ("м", "meter", "metre"), 1.0),
    "mm": UnitDef("mm", LENGTH, ("мм",), 1e-3),
    "cm": UnitDef("cm", LENGTH, ("см",), 1e-2),
    "um": UnitDef("um", LENGTH, ("мкм", "µm", "micron", "microns"), 1e-6),
    "nm": UnitDef("nm", LENGTH, ("нм",), 1e-9),
    # mass-fraction — массовая доля, base = dimensionless ratio (1).
    "%": UnitDef(
        "%", MASS_FRACTION, ("percent", "pct", "масс.%", "мас.%", "% масс.", "%масс"), 1e-2
    ),
    "ppm": UnitDef("ppm", MASS_FRACTION, ("ппм", "млн-1"), 1e-6),
    "ppb": UnitDef("ppb", MASS_FRACTION, ("ппб",), 1e-9),
    # current-density — плотность тока, base A/m^2. 1 mA/cm^2 = 10 A/m^2.
    "A/m^2": UnitDef("A/m^2", CURRENT_DENSITY, ("А/м2", "а/м2", "a/m2", "А/м²"), 1.0),
    "mA/cm^2": UnitDef("mA/cm^2", CURRENT_DENSITY, ("мА/см2", "ма/см2", "ma/cm2", "мА/см²"), 10.0),
}


def _fold(unit: str) -> str:
    """Fold a unit token for lookup — свёртка написаний (§7.11).

    NFKC-normalize, strip, drop ``^`` and spaces, then lowercase, so that
    ``A/m^2``/``A/m2``/``A/m²`` collapse to one key and ``МПа``/``mpa`` match.
    NFKC maps superscripts (``²`` → ``2``) and the micro sign (``µ`` → ``μ``).
    """
    u = unicodedata.normalize("NFKC", str(unit)).strip()
    return u.replace("^", "").replace(" ", "").lower()


def _build_alias_lookup() -> dict[str, str]:
    """Folded canonical/alias token → canonical — таблица поиска (§7.11).

    Raises :class:`RuntimeError` if two distinct canonicals fold to one token,
    which would make the registry ambiguous (a config bug, caught at import).
    """
    lookup: dict[str, str] = {}
    for canonical, unit_def in UNIT_REGISTRY.items():
        for token in (canonical, *unit_def.aliases):
            key = _fold(token)
            existing = lookup.get(key)
            if existing is not None and existing != canonical:
                raise RuntimeError(
                    f"unit alias collision: {token!r} → {canonical!r} vs {existing!r}"
                )
            lookup[key] = canonical
    return lookup


_ALIAS_LOOKUP: dict[str, str] = _build_alias_lookup()


def resolve_alias(unit: str | None) -> str | None:
    """Resolve *unit* (RU/EN alias or canonical) to its canonical string (§7.11).

    NFKC-folded, case-insensitive. Returns ``None`` for an unknown or empty unit
    (``resolve_alias("МПа") == "MPa"``, ``resolve_alias("banana") is None``).
    """
    if unit is None:
        return None
    return _ALIAS_LOOKUP.get(_fold(unit))


def dimension_of(unit: str | None) -> str:
    """Return the physical dimension of *unit* (§7.11), resolving aliases first.

    Raises :class:`ValueError` for an unregistered unit — размерность неизвестна.
    """
    canonical = resolve_alias(unit)
    if canonical is None:
        raise ValueError(f"unknown unit: {unit!r}")
    return UNIT_REGISTRY[canonical].dimension


def registry_version() -> str:
    """Stable content hash of the whole registry — версия каталога (§7.11).

    Deterministic across processes/orderings: canonicals are sorted and each
    entry serialized with sorted keys (``ensure_ascii`` so RU aliases hash
    identically everywhere). Format ``"ur1:<16-hex>"``; changes iff the registry
    content changes, so callers can pin/compare catalogue versions.
    """
    payload = json.dumps(
        [UNIT_REGISTRY[c].as_dict() for c in sorted(UNIT_REGISTRY)],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"ur1:{digest[:16]}"


__all__ = [
    "CURRENT_DENSITY",
    "DIMENSIONS",
    "LENGTH",
    "MASS_FRACTION",
    "PRESSURE",
    "SI_BASE_UNIT",
    "TEMPERATURE",
    "UNIT_REGISTRY",
    "UnitDef",
    "dimension_of",
    "registry_version",
    "resolve_alias",
]

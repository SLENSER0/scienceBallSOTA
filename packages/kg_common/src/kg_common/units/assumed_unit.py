"""Assumed unit embedded in an explicit property name (§7.2).

§7.2 permits a *safe* assumed unit only when the property name itself
explicitly spells the unit as a suffix/token — e.g. ``hardness_HV``,
``yield_strength_MPa``, ``temperature_C``. This is distinct from
:mod:`unit_suggest`, which infers a unit from the numeric *value*; here the
name is authoritative and nothing is guessed from magnitudes. Whenever a unit
is derived this way it is *always* flagged ``unit_assumed=True`` and carries
``normalization_method='rule'`` so downstream review can see the assumption.

The scan splits the property name on ``_`` / space separators into tokens and
matches them against a small ASCII unit set (``HV``, ``HRC``, ``HB``, ``MPa``,
``GPa``, ``C``, ``K``). Cyrillic pressure spellings (``МПа``/``ГПа``) are folded
to their ASCII canonical via :func:`resolve_alias` (with a supplement for
``ГПа``, which is not a registry canonical). The rightmost matching token wins,
since the unit conventionally sits at the end of the name. When no token names a
unit the result is ``assumed_unit=None`` / ``unit_assumed=False``.

Единица измерения, явно зашитая в имя свойства (§7.2): безопасно берётся только
если имя прямо называет единицу как суффикс, всегда с флагом ``unit_assumed`` и
методом ``rule``. Значение никогда не парсится — в отличие от unit_suggest.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from kg_common.units.registry import resolve_alias

# ASCII unit tokens that may legitimately be embedded in a property name (§7.2).
# Matched exactly (case-sensitive) so a stray lowercase ``c``/``k`` word token
# is not mistaken for a unit; the value itself is never inspected.
EMBEDDED_UNITS: frozenset[str] = frozenset({"HV", "HRC", "HB", "MPa", "GPa", "C", "K"})

# Cyrillic pressure spellings → ASCII canonical. ``МПа`` also resolves via the
# registry, but ``ГПа`` is not a registry canonical, so it is supplemented here.
_CYRILLIC_ALIASES: dict[str, str] = {"МПа": "MPa", "ГПа": "GPa"}

# Split on one-or-more ``_`` / whitespace separators (§7.2 token boundaries).
_SEPARATORS = re.compile(r"[ _]+")


@dataclass(frozen=True)
class AssumedUnit:
    """Outcome of scanning a property name for an embedded unit (§7.2).

    ``assumed_unit`` is the canonical unit named in the property name (or
    ``None``); ``unit_assumed`` is always ``True`` exactly when a unit was found;
    ``normalization_method`` is ``'rule'`` for a name-embedded assumption, else
    ``None``.

    Результат поиска единицы, зашитой в имя свойства.
    """

    property_name: str
    assumed_unit: str | None
    unit_assumed: bool
    normalization_method: str | None

    def as_dict(self) -> dict[str, str | bool | None]:
        """Return a plain, JSON-friendly dict of all fields."""
        return asdict(self)


def _canonical_token(token: str) -> str | None:
    """Map a single name token to a canonical embedded unit, or ``None``.

    ASCII units match exactly; cyrillic pressure spellings fold to ASCII via
    :func:`resolve_alias` (with a ``ГПа`` supplement). Never inspects a value.
    """
    if token in EMBEDDED_UNITS:
        return token
    alias = resolve_alias(token)
    if alias in EMBEDDED_UNITS:
        return alias
    return _CYRILLIC_ALIASES.get(token)


def embedded_unit(property_name: str) -> AssumedUnit:
    """Scan *property_name* for a unit spelled as a suffix/token (§7.2).

    Returns an :class:`AssumedUnit`. When a token names a unit the rightmost
    match wins, ``unit_assumed=True`` and ``normalization_method='rule'``;
    otherwise ``assumed_unit=None``, ``unit_assumed=False`` and no method.

    ``embedded_unit("hardness_HV").assumed_unit == "HV"``;
    ``embedded_unit("hardness").assumed_unit is None``.
    """
    tokens = [t for t in _SEPARATORS.split(property_name) if t]
    for token in reversed(tokens):
        canonical = _canonical_token(token)
        if canonical is not None:
            return AssumedUnit(
                property_name=property_name,
                assumed_unit=canonical,
                unit_assumed=True,
                normalization_method="rule",
            )
    return AssumedUnit(
        property_name=property_name,
        assumed_unit=None,
        unit_assumed=False,
        normalization_method=None,
    )


__all__ = [
    "EMBEDDED_UNITS",
    "AssumedUnit",
    "embedded_unit",
]

"""Suggest a measurement unit for a bare value from its property (§7.14).

When a property value is extracted *without* a unit (голое значение — bare
number), the curator still needs a sensible default unit to attach. This module
answers that: given a canonical ``property_id`` (and, optionally, the numeric
value), it returns the conventional unit plus ranked alternatives.

The candidate units come from the controlled property vocabulary — it reuses
:meth:`kg_extractors.property_vocab.PropertyVocabulary.allowed_units` (which
mirrors ``kg_common.units.policy.PROPERTY_UNIT_POLICY``) as the single source of
truth, so extraction, unit-gating and this suggestion stay aligned. The **first**
allowed unit is the conventional default (``prop:hardness`` → ``HV``,
``prop:tensile_strength`` → ``MPa``); the rest become :attr:`alternatives`.

An optional *value* sharpens the guess (подсказка по значению): a bare hardness
of ``60`` is a Rockwell-C number (``HRC``), not ``HV``, because only ``HRC``'s
typical range brackets ``60``. When exactly one allowed unit's typical range
contains the value, that unit is promoted to the suggestion and the confidence is
raised. An unknown property (no allowed units) yields ``None``.

Pure Python — no LLM, no I/O beyond the packaged vocabulary YAML.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_extractors.property_vocab import default_property_vocab

# --- confidence levels (уверенность), all in [0, 1] --------------------------
#: A property with a single allowed unit — the unit is forced, no ambiguity.
_CONF_SINGLE = 1.0
#: Multiple allowed units, no value hint — the conventional first choice.
_CONF_DEFAULT = 0.5
#: A value uniquely bracketed by one allowed unit's typical range (подтверждено).
_CONF_VALUE = 0.9

# --- value hints (диапазоны значений) ----------------------------------------
#: ``property_id`` -> ``((unit, lo, hi), ...)`` typical inclusive value ranges.
#: Used only to break ties when a bare number is supplied; a unit is picked iff
#: it is the *only* allowed unit whose ``[lo, hi]`` brackets the value.
_VALUE_HINTS: dict[str, tuple[tuple[str, float, float], ...]] = {
    # Vickers 100–1200, Brinell 80–650, Rockwell-C 20–70 (твёрдость).
    "prop:hardness": (
        ("HV", 100.0, 1200.0),
        ("HB", 80.0, 650.0),
        ("HRC", 20.0, 70.0),
    ),
    # GPa is sub-10; MPa / N/mm² are tens–thousands; kgf/mm² up to ~510.
    "prop:tensile_strength": (
        ("GPa", 0.05, 5.0),
        ("MPa", 20.0, 5000.0),
        ("N/mm2", 20.0, 5000.0),
        ("kgf/mm2", 2.0, 510.0),
    ),
    # g/cm³ is sub-30; kg/m³ is hundreds–tens-of-thousands (плотность).
    "prop:density": (
        ("g/cm3", 0.1, 30.0),
        ("kg/m3", 100.0, 30000.0),
    ),
}


@dataclass(frozen=True)
class UnitSuggestion:
    """A suggested unit for a bare property value (§7.14).

    Fields
    ------
    property_id
        The canonical property this suggestion is for (``prop:hardness``).
    unit
        The suggested unit (предлагаемая единица) — the conventional default or,
        when a value disambiguates, the value-informed unit.
    confidence
        Suggestion confidence in ``[0, 1]``: ``1.0`` when the property allows a
        single unit, ``0.9`` when a value uniquely selects a unit, ``0.5`` for a
        conventional default among several units.
    alternatives
        Other allowed units in vocabulary order, excluding :attr:`unit`
        (варианты на выбор).
    """

    property_id: str
    unit: str
    confidence: float
    alternatives: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Full structured view (все поля)."""
        return {
            "property_id": self.property_id,
            "unit": self.unit,
            "confidence": self.confidence,
            "alternatives": list(self.alternatives),
        }


def _to_float(value: object) -> float | None:
    """Coerce *value* to ``float`` (comma decimal allowed), else ``None``.

    ``bool`` is rejected (a flag is not a measurement), as are non-numeric
    strings and ``None``.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _value_pick(property_id: str, value: float, allowed: tuple[str, ...]) -> str | None:
    """Return the allowed unit uniquely bracketing *value*, or ``None``.

    Only units present in *allowed* are considered; when zero or more than one
    range contains *value* the tie is left unbroken (returns ``None``).
    """
    hints = _VALUE_HINTS.get(property_id)
    if not hints:
        return None
    matches = [u for (u, lo, hi) in hints if u in allowed and lo <= value <= hi]
    return matches[0] if len(matches) == 1 else None


def suggest_unit(property_id: str, value: object = None) -> UnitSuggestion | None:
    """Suggest a unit for a bare *value* of *property_id* (§7.14).

    Looks up the property's allowed units in the controlled vocabulary. The first
    allowed unit is the conventional default; when *value* is a number that is
    uniquely bracketed by one allowed unit's typical range, that unit is promoted
    instead and the confidence is raised. Returns ``None`` for a falsy or unknown
    ``property_id`` (a property with no allowed units). Pure function.
    """
    if not property_id:
        return None
    allowed = default_property_vocab().allowed_units(property_id)
    if not allowed:
        return None

    picked: str | None = None
    num = _to_float(value)
    if num is not None:
        picked = _value_pick(property_id, num, allowed)

    if picked is not None:
        unit = picked
        confidence = _CONF_VALUE
    else:
        unit = allowed[0]
        confidence = _CONF_SINGLE if len(allowed) == 1 else _CONF_DEFAULT

    alternatives = tuple(u for u in allowed if u != unit)
    return UnitSuggestion(
        property_id=property_id,
        unit=unit,
        confidence=confidence,
        alternatives=alternatives,
    )


__all__ = ["UnitSuggestion", "suggest_unit"]

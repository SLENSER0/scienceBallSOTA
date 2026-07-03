"""Alloy-family classification from raw element composition (§8.3).

Классификация семейства сплава по составу элементов.

:mod:`kg_extractors.alloy_normalize` maps a designation *string* (``AA2024`` /
``316L`` / ``Ti-6Al-4V``) to a family. That path is blind when no designation was
printed — a very common situation right after
:mod:`kg_extractors.composition_parser`, which yields only element fractions. This
module closes that gap: given a ``{element: weight_percent}`` mapping it picks the
base (max-fraction) element and derives the broad family — regex-free, purely from
the numeric composition.

Rules (§8.3):

- ``Al`` — AA series by the dominant alloying element: ``Cu`` → ``2xxx``,
  ``Mg``+``Si`` → ``6xxx``, ``Zn`` → ``7xxx``, ``Mn`` → ``3xxx``, ``Si`` →
  ``4xxx``, ``Mg`` (no ``Si``) → ``5xxx``; otherwise commercially-pure ``1xxx``.
- ``Fe`` — ``Cr`` ≥ 10.5 wt% → ``stainless_steel`` (subfamily ``austenitic`` when
  ``Ni`` ≥ 8, else ``ferritic_martensitic``); below that → ``carbon_steel``.
- ``Ti`` → ``titanium_alloy``; ``Ni`` → ``nickel_superalloy``.
- empty / unrecognized base → ``family == "unknown"``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# §8.3 thresholds (weight percent). Stainless needs ≥10.5 wt% Cr; austenitic grades
# carry ≥8 wt% Ni. Порог хрома/никеля для нержавеющих сталей.
_CR_STAINLESS = 10.5
_NI_AUSTENITIC = 8.0


@dataclass(frozen=True)
class AlloyFamily:
    """A composition-derived alloy family classification (§8.3).

    ``base_element`` — the max-fraction element (``None`` for an empty
    composition); ``family`` — broad family (``2xxx`` / ``stainless_steel`` /
    ``titanium_alloy`` / ``unknown`` / …); ``subfamily`` — steel microstructure
    class where applicable, else ``None``; ``confidence`` — base-element dominance
    as a fraction of the total composition (``0.0`` when unknown).
    """

    base_element: str | None
    family: str
    subfamily: str | None
    confidence: float

    def as_dict(self) -> dict[str, object]:
        """Serialize to ``{base_element, family, subfamily, confidence}``."""
        return asdict(self)


def _classify_aluminium(fractions: dict[str, float], base: str) -> tuple[str, str | None]:
    """Assign an Al AA series from its dominant alloying element (§8.3)."""
    alloying = {el: frac for el, frac in fractions.items() if el != base}
    if not alloying:
        return "1xxx", None  # commercially pure — no significant alloying addition
    dominant = max(alloying, key=lambda el: alloying[el])
    has_mg = alloying.get("Mg", 0.0) > 0.0
    has_si = alloying.get("Si", 0.0) > 0.0
    if dominant == "Cu":
        return "2xxx", None
    if dominant == "Zn":
        return "7xxx", None
    if dominant == "Mn":
        return "3xxx", None
    if dominant == "Mg":
        return ("6xxx" if has_si else "5xxx"), None  # Mg+Si → 6xxx, Mg alone → 5xxx
    if dominant == "Si":
        return ("6xxx" if has_mg else "4xxx"), None
    return "1xxx", None


def _classify_iron(fractions: dict[str, float]) -> tuple[str, str | None]:
    """Split Fe-based alloys into stainless (austenitic/ferritic) vs carbon (§8.3)."""
    if fractions.get("Cr", 0.0) >= _CR_STAINLESS:
        subfamily = (
            "austenitic" if fractions.get("Ni", 0.0) >= _NI_AUSTENITIC else ("ferritic_martensitic")
        )
        return "stainless_steel", subfamily
    return "carbon_steel", None


def classify_from_composition(fractions: dict[str, float]) -> AlloyFamily:
    """Classify an alloy family from ``{element: weight_percent}`` fractions (§8.3).

    Классифицировать семейство сплава по долям элементов состава.

    The base element is the max-fraction constituent. ``confidence`` reports how
    dominant that base is (its share of the summed composition); an empty mapping
    yields ``base_element=None``, ``family="unknown"``, ``confidence=0.0``.
    """
    if not fractions:
        return AlloyFamily(base_element=None, family="unknown", subfamily=None, confidence=0.0)

    base = max(fractions, key=lambda el: fractions[el])
    total = sum(fractions.values())
    confidence = round(fractions[base] / total, 4) if total > 0 else 0.0

    if base == "Al":
        family, subfamily = _classify_aluminium(fractions, base)
    elif base == "Fe":
        family, subfamily = _classify_iron(fractions)
    elif base == "Ti":
        family, subfamily = "titanium_alloy", None
    elif base == "Ni":
        family, subfamily = "nickel_superalloy", None
    else:
        family, subfamily, confidence = "unknown", None, 0.0

    return AlloyFamily(base_element=base, family=family, subfamily=subfamily, confidence=confidence)

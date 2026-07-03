"""Atmosphere canonicalizer for the processing vocabulary (§6.5).

``processing_steps._find_atmosphere`` returns only a raw gas token (the leftmost
gas surface it spots); it neither maps that surface to a stable canonical id nor
tells the caller how the atmosphere behaves chemically. This rule closes both
gaps: it turns a free-text atmosphere cue (RU + EN, incl. short symbols like
``Ar`` / ``N2`` / ``H2`` and phrases like «under vacuum» / «in air») into a
canonical atmosphere id plus a coarse *reactivity* class used downstream to
reason about oxidation / reduction / inertness during a processing step.

Canonical ids : ``air argon nitrogen vacuum hydrogen helium oxygen co2 unknown``.
Reactivity    : ``inert`` (Ar/N2/He), ``oxidizing`` (air/O2/CO2),
``reducing`` (H2), ``vacuum`` (evacuated — no gas), ``unknown`` (no cue).

Kuzu note: these are custom node props, not queryable columns — a persisted
``AtmosphereNorm`` is written whole and read back via ``get_node()``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Canonical atmosphere id -> reactivity class (§6.5). ``nitrogen`` and ``helium``
# are treated as practically inert for processing-atmosphere purposes; ``co2`` is
# bucketed oxidizing (carburizing/oxidizing behaviour vs. a reducing H2 stream).
_REACTIVITY: dict[str, str] = {
    "air": "oxidizing",
    "oxygen": "oxidizing",
    "co2": "oxidizing",
    "argon": "inert",
    "nitrogen": "inert",
    "helium": "inert",
    "hydrogen": "reducing",
    "vacuum": "vacuum",
    "unknown": "unknown",
}

# Surface cue -> canonical id (RU stems + EN words + short gas symbols). Order is
# significant: the FIRST pattern that matches wins, so more specific / distinctive
# symbols are listed ahead of broad ones. Word boundaries keep ``\bAr\b`` from
# firing inside «air» and ``\bO2\b`` from firing inside «CO2».
_ATMOSPHERE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("vacuum", re.compile(r"\bvacuum\b|вакуум", re.IGNORECASE)),
    ("hydrogen", re.compile(r"\bhydrogen\b|\bH2\b|водород", re.IGNORECASE)),
    ("co2", re.compile(r"\bco2\b|carbon\s+dioxide|углекислы", re.IGNORECASE)),
    ("oxygen", re.compile(r"\boxygen\b|\bO2\b|кислород", re.IGNORECASE)),
    ("nitrogen", re.compile(r"\bnitrogen\b|\bN2\b|азот", re.IGNORECASE)),
    ("argon", re.compile(r"\bargon\b|\bAr\b|аргон", re.IGNORECASE)),
    ("helium", re.compile(r"\bhelium\b|гелий|гелие", re.IGNORECASE)),
    ("air", re.compile(r"\bair\b|воздух", re.IGNORECASE)),
]


@dataclass(frozen=True)
class AtmosphereNorm:
    """A normalized processing atmosphere (§6.5).

    ``raw`` is the input text as given. ``canonical`` is a stable atmosphere id in
    ``{air, argon, nitrogen, vacuum, hydrogen, helium, oxygen, co2, unknown}``.
    ``reactivity`` is the coarse chemical class in ``{inert, oxidizing, reducing,
    vacuum, unknown}`` implied by that atmosphere.
    """

    raw: str
    canonical: str
    reactivity: str

    def as_dict(self) -> dict[str, str]:
        """Serialize to exactly ``{'raw', 'canonical', 'reactivity'}`` (§6.5)."""
        return {
            "raw": self.raw,
            "canonical": self.canonical,
            "reactivity": self.reactivity,
        }


def normalize_atmosphere(text: str) -> AtmosphereNorm:
    """Normalize an atmosphere cue (RU + EN) into an :class:`AtmosphereNorm`.

    Returns ``canonical == 'unknown'`` (reactivity ``unknown``) when no known
    atmosphere cue is present (e.g. «quenched somehow»). The first matching
    pattern in :data:`_ATMOSPHERE_PATTERNS` wins.
    """
    raw = text or ""
    for canonical, pattern in _ATMOSPHERE_PATTERNS:
        if pattern.search(raw):
            return AtmosphereNorm(
                raw=raw,
                canonical=canonical,
                reactivity=_REACTIVITY[canonical],
            )
    return AtmosphereNorm(raw=raw, canonical="unknown", reactivity="unknown")

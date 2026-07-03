"""Quench / cooling-medium classifier (§6.5).

``processing_steps.py`` canonicalizes the *operation* «quenching» and the
*atmosphere*, but it does not identify the cooling MEDIUM (what the hot part is
plunged into / cooled by) nor the qualitative cooling RATE that medium implies.
§6.5 lists water-quench / air-cool / furnace-cool as ``cooling_rate`` cues; this
rule turns a free-text cue (RU + EN) into a canonical medium and a coarse
severity class ordered by heat-transfer capability.

Severity ranking (fastest → slowest heat extraction, §6.5):
``brine > water > oil > air > furnace``. ``severity_class`` buckets these into
``fast`` (brine, water), ``moderate`` (oil), ``slow`` (air, furnace). Custom
node props are read via ``get_node()`` — they are not Kuzu-queryable columns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Canonical media in order of decreasing heat-transfer (§6.5). The rank is the
# reverse index so brine=5 (fastest) … furnace=1 (slowest); unknown=0.
_MEDIA_ORDER: tuple[str, ...] = ("furnace", "air", "oil", "water", "brine")

_SEVERITY_CLASS: dict[str, str] = {
    "brine": "fast",
    "water": "fast",
    "oil": "moderate",
    "air": "slow",
    "furnace": "slow",
    "unknown": "unknown",
}

# Cue surfaces -> canonical medium (RU stems + EN words). Order matters: brine
# ("рассол") is checked before water so «rassol» never falls through to «вод».
_MEDIUM_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("brine", re.compile(r"\bbrine\b|рассол", re.IGNORECASE)),
    ("water", re.compile(r"\bwater\b|вод", re.IGNORECASE)),
    ("oil", re.compile(r"\boil\b|масл", re.IGNORECASE)),
    ("furnace", re.compile(r"\bfurnace\b|печ", re.IGNORECASE)),
    ("air", re.compile(r"\bair\b|воздух", re.IGNORECASE)),
]


def _rank_for(medium: str) -> int:
    """Heat-transfer rank: higher == faster cooling; ``unknown`` == 0 (§6.5)."""
    if medium in _MEDIA_ORDER:
        return _MEDIA_ORDER.index(medium) + 1
    return 0


@dataclass(frozen=True)
class CoolingMedium:
    """Classified cooling medium + its qualitative severity (§6.5).

    ``medium`` is a canonical id (``water``/``oil``/``air``/``furnace``/``brine``
    or ``unknown``). ``severity_class`` is ``fast``/``moderate``/``slow`` (or
    ``unknown``). ``severity_rank`` orders heat-transfer capability, higher being
    faster: brine > water > oil > air > furnace, with ``unknown`` == 0.
    """

    raw: str
    medium: str
    severity_class: str
    severity_rank: int

    def as_dict(self) -> dict[str, object]:
        return {
            "raw": self.raw,
            "medium": self.medium,
            "severity_class": self.severity_class,
            "severity_rank": self.severity_rank,
        }


def classify_cooling(text: str) -> CoolingMedium:
    """Classify a cooling-medium cue (RU + EN) into a :class:`CoolingMedium`.

    Returns ``medium == 'unknown'`` (rank 0, class ``unknown``) when no known
    medium cue is present (e.g. «quenched somehow»).
    """
    raw = text or ""
    for medium, pattern in _MEDIUM_PATTERNS:
        if pattern.search(raw):
            return CoolingMedium(
                raw=raw,
                medium=medium,
                severity_class=_SEVERITY_CLASS[medium],
                severity_rank=_rank_for(medium),
            )
    return CoolingMedium(
        raw=raw,
        medium="unknown",
        severity_class=_SEVERITY_CLASS["unknown"],
        severity_rank=0,
    )

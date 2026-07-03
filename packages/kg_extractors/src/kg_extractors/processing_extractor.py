"""Processing-regime + parameter extraction from prose (§6.5).

Recognizes metallurgical/mineral-processing methods (RU/EN) and the process
parameters stated near them — temperature, duration, current density, pressure —
returning a structured :class:`ProcessingMention` with an evidence span. Feeds the
``ProcessingRegime``→``HAS_PARAMETER``→``Parameter`` graph shape (§3.5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# method surface → canonical process key (RU + EN).
_METHODS: dict[str, str] = {
    "электроэкстракц": "electrowinning",
    "электролиз": "electrolysis",
    "электрорафинир": "electrorefining",
    "выщелачивани": "leaching",
    "автоклавн": "autoclave_leaching",
    "обжиг": "roasting",
    "плавк": "smelting",
    "флотаци": "flotation",
    "цементаци": "cementation",
    "экстракци": "solvent_extraction",
    "старени": "aging",
    "отжиг": "annealing",
    "закалк": "quenching",
    "electrowinning": "electrowinning",
    "electrolysis": "electrolysis",
    "leaching": "leaching",
    "roasting": "roasting",
    "smelting": "smelting",
    "flotation": "flotation",
    "aging": "aging",
    "annealing": "annealing",
    "quenching": "quenching",
}

_PARAM_PATTERNS: list[tuple[str, re.Pattern]] = [
    # degree sign optional so "500 C" / "60 °C" / "180 град" all match (C = lat/cyr)
    (
        "temperature_c",
        re.compile(r"(\d+[.,]?\d*)\s*°?\s*(?:C\b|С\b|град|℃|deg\s*C)", re.IGNORECASE),
    ),
    ("duration", re.compile(r"(\d+[.,]?\d*)\s*(?:ч\b|час|h\b|hours?|мин\b|min\b)", re.IGNORECASE)),
    (
        "current_density",
        re.compile(r"(\d+[.,]?\d*)\s*(?:А/?м2|А/?м²|A/?m2|мА/?см2)", re.IGNORECASE),
    ),
    ("pressure", re.compile(r"(\d+[.,]?\d*)\s*(?:МПа|MPa|атм|bar|бар|кПа|kPa)", re.IGNORECASE)),
    ("ph", re.compile(r"\bpH\s*[:=]?\s*(\d+[.,]?\d*)", re.IGNORECASE)),
]

_WINDOW = 120  # chars around the method mention to scan for parameters


@dataclass
class ProcessingMention:
    method: str
    surface: str
    span: tuple[int, int]
    parameters: dict[str, float] = field(default_factory=dict)


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def extract_processing(text: str) -> list[ProcessingMention]:
    """Find processing-method mentions + their nearby parameters."""
    if not text:
        return []
    low = text.lower()
    found: list[ProcessingMention] = []
    used_methods: set[tuple[str, int]] = set()
    for surface_key, canon in _METHODS.items():
        start = 0
        while True:
            idx = low.find(surface_key, start)
            if idx == -1:
                break
            start = idx + len(surface_key)
            if (canon, idx // 60) in used_methods:  # de-dup near-duplicates
                continue
            used_methods.add((canon, idx // 60))
            lo = max(0, idx - _WINDOW)
            hi = min(len(text), idx + len(surface_key) + _WINDOW)
            window = text[lo:hi]
            params: dict[str, float] = {}
            for name, pat in _PARAM_PATTERNS:
                m = pat.search(window)
                if m and name not in params:
                    params[name] = _num(m.group(1))
            found.append(
                ProcessingMention(
                    method=canon,
                    surface=text[idx : idx + len(surface_key)],
                    span=(idx, idx + len(surface_key)),
                    parameters=params,
                )
            )
    found.sort(key=lambda p: p.span[0])
    return found

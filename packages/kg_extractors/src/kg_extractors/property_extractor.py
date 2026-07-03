"""Property-mention extraction from prose (§6.6).

Scans text for controlled-vocabulary material/process properties (RU/EN
synonyms) and returns canonical ``property_id`` mentions with evidence spans —
so a property is recognized even when no numeric value is attached. Canonical ids
match the property vocabulary used by ER (``kg_er.store.property_vocab``) and the
seed graph, keeping extraction and resolution aligned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# canonical property_id → RU/EN surface synonyms (lowercased, matched whole-word).
PROPERTY_VOCAB: dict[str, list[str]] = {
    "prop:hardness": ["твердость", "твёрдость", "hardness", "микротвердость", "hv", "hrc", "hb"],
    "prop:tensile_strength": [
        "предел прочности",
        "прочность на разрыв",
        "tensile strength",
        "uts",
        "временное сопротивление",
    ],
    "prop:yield_strength": ["предел текучести", "yield strength", "proof stress"],
    "prop:elongation": ["относительное удлинение", "удлинение", "elongation", "ductility"],
    "prop:conductivity": ["электропроводность", "проводимость", "conductivity"],
    "prop:density": ["плотность", "density"],
    "prop:current_density": ["плотность тока", "current density"],
    "prop:recovery": ["извлечение", "степень извлечения", "recovery", "выход"],
    "prop:grade": ["содержание", "grade", "концентрация металла"],
    "prop:flow_velocity": ["скорость циркуляции", "скорость потока", "flow velocity"],
    "prop:removal_efficiency": [
        "степень очистки",
        "эффективность улавливания",
        "removal efficiency",
        "степень удаления",
    ],
    "prop:tds": ["сухой остаток", "минерализация", "tds", "total dissolved solids"],
}

# Build one regex per canonical id (longest synonyms first to prefer specific matches).
_COMPILED: list[tuple[str, re.Pattern]] = [
    (
        pid,
        re.compile(
            r"(?<![а-яёa-z0-9])("
            + "|".join(re.escape(s) for s in sorted(syns, key=len, reverse=True))
            + r")(?![а-яёa-z0-9])",
            re.IGNORECASE,
        ),
    )
    for pid, syns in PROPERTY_VOCAB.items()
]


@dataclass(frozen=True)
class PropertyMention:
    property_id: str
    surface: str
    span: tuple[int, int]


def extract_properties(text: str) -> list[PropertyMention]:
    """Return canonical property mentions found in *text* (deduped by span, ordered)."""
    if not text:
        return []
    # gather every candidate across all vocab entries, then claim longest-first so
    # a specific term ("плотность тока") wins over its substring ("плотность")
    # regardless of vocab order.
    cands: list[tuple[str, tuple[int, int], str]] = [
        (pid, m.span(1), m.group(1)) for pid, pat in _COMPILED for m in pat.finditer(text)
    ]
    cands.sort(key=lambda c: c[1][1] - c[1][0], reverse=True)
    claimed: list[tuple[int, int]] = []
    chosen: list[PropertyMention] = []
    for pid, span, surface in cands:
        if any(span[0] < e and s < span[1] for s, e in claimed):
            continue
        claimed.append(span)
        chosen.append(PropertyMention(pid, surface, span))
    chosen.sort(key=lambda p: p.span[0])
    return chosen

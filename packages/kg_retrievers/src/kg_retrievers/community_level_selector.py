"""Community-level selector for GraphRAG hierarchies (§11.7).

GraphRAG строит *иерархию сообществ* (a hierarchy of communities): level ``0`` holds
fine-grained, entity-level clusters and each higher level rolls them up into broader,
more global summaries. Given a natural-language query this module decides *how broad*
the answer should be and picks a matching ``community_level`` in ``[0, max_level]`` where
a **higher** level is **more general**.

The heuristic is lexical and bilingual (RU/EN). *Broad* markers such as ``overview`` /
``обзор`` / ``в целом`` / ``направления`` / ``landscape`` raise the breadth of the query,
while *specific* signals — numeric tokens (``320``), physical units (``MPa``, ``°C``) and
concrete material tokens — lower it. The public :func:`breadth_score` collapses those
signals into a single float in ``[0, 1]`` (``1`` = maximally global). :func:`select_level`
buckets that score into a coarse ``breadth`` label (``'narrow'`` / ``'regional'`` /
``'global'``) and the corresponding community level. An explicit ``override`` short-circuits
the heuristic entirely, clamped to ``[0, max_level]`` and stamped ``reason='override'``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- Lexical signal tables (RU + EN) --------------------------------------------------

# Broad / global markers. Their presence argues for a high, rolled-up community level:
# the caller wants the landscape view rather than one entity's exact number.
BROAD_MARKERS: tuple[str, ...] = (
    "overview",
    "landscape",
    "big picture",
    "state of the field",
    "trends",
    "directions",
    "summary",
    "in general",
    "обзор",
    "в целом",
    "направления",
    "направлений",
    "в теме",
    "тенденции",
)

# Narrow / specific lexical markers. Their presence argues for level 0: the caller wants
# a single pinned value or entity, not a broad summary.
NARROW_MARKERS: tuple[str, ...] = (
    "exact",
    "exactly",
    "specifically",
    "value of",
    "for sample",
    "конкретно",
    "точное значение",
    "для образца",
)

# Physical-unit tokens. A query carrying units is asking about a concrete measurement and
# so reads as narrow. Matched case-insensitively as whole-ish tokens.
UNIT_MARKERS: tuple[str, ...] = (
    "mpa",
    "gpa",
    "kpa",
    "pa",
    "°c",
    "kelvin",
    "%",
    "nm",
    "µm",
    "um",
    "mm",
    "cm",
    "kg",
    "mol",
    "wt%",
    "at%",
    "hv",
    "hrc",
)

# Concrete material / entity tokens. Their presence also argues for a narrow answer.
MATERIAL_MARKERS: tuple[str, ...] = (
    "alloy",
    "steel",
    "titanium",
    "ceramic",
    "polymer",
    "сплав",
    "сталь",
    "образец",
)

# Neutral midpoint of :func:`breadth_score`: no broad and no narrow signals -> ``0.5``.
_NEUTRAL: float = 0.5
# Weight applied per broad / narrow signal when nudging the neutral midpoint.
_STEP: float = 0.2
# Score at/above which a query reads as fully ``global``; at/below which as ``narrow``.
_GLOBAL_AT: float = 0.6
_NARROW_AT: float = 0.4
# Reason stamped when an explicit override wins over the heuristic.
_OVERRIDE_REASON: str = "override"

_DIGIT_RE = re.compile(r"\d")


def _clamp_int(level: int, max_level: int) -> int:
    """Clamp ``level`` into the closed range ``[0, max_level]``."""
    if level < 0:
        return 0
    if level > max_level:
        return max_level
    return level


def _clamp_unit(value: float) -> float:
    """Clamp ``value`` into the closed range ``[0.0, 1.0]``."""
    return min(1.0, max(0.0, value))


def _count_markers(text: str, markers: tuple[str, ...]) -> int:
    """Count how many distinct ``markers`` appear as substrings of ``text``."""
    return sum(1 for marker in markers if marker in text)


def _broad_signals(text: str) -> int:
    """Count broad/global lexical signals in already-lowercased ``text``."""
    return _count_markers(text, BROAD_MARKERS)


def _narrow_signals(text: str) -> int:
    """Count narrow/specific signals: lexical markers, units, materials, and numbers."""
    narrow = _count_markers(text, NARROW_MARKERS)
    narrow += _count_markers(text, UNIT_MARKERS)
    narrow += _count_markers(text, MATERIAL_MARKERS)
    if _DIGIT_RE.search(text) is not None:
        narrow += 1
    return narrow


def breadth_score(query: str) -> float:
    """Score how broad/global ``query`` reads, in ``[0, 1]`` (§11.7).

    Starts from a neutral ``0.5`` and nudges up ``_STEP`` per broad signal and down
    ``_STEP`` per narrow signal (numeric/unit/material/specific tokens), then clamps to
    ``[0, 1]``. A query with no signals of either kind scores exactly ``0.5``. A broad
    query therefore always scores strictly above an otherwise-narrow one.
    """
    lowered = query.casefold()
    broad = _broad_signals(lowered)
    narrow = _narrow_signals(lowered)
    raw = _NEUTRAL + _STEP * broad - _STEP * narrow
    return _clamp_unit(raw)


def _breadth_label(score: float) -> str:
    """Bucket a breadth ``score`` into a coarse label (§11.7)."""
    if score >= _GLOBAL_AT:
        return "global"
    if score <= _NARROW_AT:
        return "narrow"
    return "regional"


def _level_for(label: str, score: float, max_level: int) -> int:
    """Map a breadth ``label`` to a community level in ``[0, max_level]``.

    ``global`` answers from the top of the hierarchy (``max_level``), ``narrow`` from the
    entity-level bottom (``0``), and ``regional`` from a proportional interior level.
    """
    if label == "global":
        return max_level
    if label == "narrow":
        return 0
    interior = round(score * max_level)
    return _clamp_int(interior, max_level)


@dataclass(frozen=True)
class LevelChoice:
    """One resolved community-level choice (§11.7).

    ``level`` — chosen ``community_level`` in ``[0, max_level]`` (higher = more general);
    ``breadth`` — coarse label (``'narrow'`` / ``'regional'`` / ``'global'``);
    ``score`` — the underlying :func:`breadth_score` in ``[0, 1]``;
    ``reason`` — short human-readable explanation (``'override'`` when forced).
    """

    level: int
    breadth: str
    score: float
    reason: str

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "breadth": self.breadth,
            "score": self.score,
            "reason": self.reason,
        }


def select_level(
    query: str,
    *,
    max_level: int = 3,
    override: int | None = None,
) -> LevelChoice:
    """Pick a GraphRAG ``community_level`` for ``query`` (§11.7).

    An explicit ``override`` wins immediately, clamped to ``[0, max_level]`` with
    ``reason='override'`` (its ``breadth`` is still derived from the query text so the
    label stays informative). Otherwise :func:`breadth_score` grades the query, the score
    is bucketed into a ``breadth`` label, and that label maps to a level: ``global`` ->
    ``max_level``, ``narrow`` -> ``0``, ``regional`` -> a proportional interior level.
    """
    score = breadth_score(query)
    label = _breadth_label(score)

    if override is not None:
        level = _clamp_int(override, max_level)
        return LevelChoice(
            level=level,
            breadth=label,
            score=score,
            reason=_OVERRIDE_REASON,
        )

    level = _level_for(label, score, max_level)
    reason = f"breadth={label!r} (score={score:.2f}) -> level {level} of {max_level}"
    return LevelChoice(level=level, breadth=label, score=score, reason=reason)

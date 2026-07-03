"""GraphRAG community-level selector (§11.7).

GraphRAG builds a *hierarchy* of communities (иерархия сообществ): level ``0`` holds
fine-grained, entity-level clusters while higher levels roll those up into broad,
global summaries. Given a natural-language query this module picks which
``community_level`` to answer from, so a "give me an overview" question is served from
the broad top of the hierarchy and a "what is the exact yield of sample S1" question is
served from the narrow, entity-level bottom.

The heuristic is deliberately lexical and bilingual (RU/EN): it counts *broad* markers
(``'overview'``, ``'landscape'``, ``'в целом'``, ``'какие направления'``, ``'trends'``,
``'summary'``) against *narrow* markers (``'specifically'``, ``'value of'``,
``'какое значение'``, ``'for sample'``). More broad markers push toward ``max_level``;
more narrow markers pull toward level ``0``; a tie (including an empty query) lands on a
mid/default level so nothing ever crashes. A ``breadth_score`` in ``[0, 1]`` summarises
how global-vs-local the query reads. An explicit ``override`` short-circuits the whole
heuristic, clamping to ``[0, max_level]`` and stamping ``reason='override'``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Broad / global markers (RU + EN). Their presence argues for a high community level:
# the caller wants the rolled-up, landscape view rather than one entity's number.
BROAD_MARKERS: tuple[str, ...] = (
    "overview",
    "landscape",
    "в целом",
    "какие направления",
    "trends",
    "summary",
    "big picture",
    "state of the field",
)

# Narrow / entity markers (RU + EN). Their presence argues for level 0: the caller
# wants a specific value pinned to a single entity or sample.
NARROW_MARKERS: tuple[str, ...] = (
    "specifically",
    "value of",
    "какое значение",
    "for sample",
    "exact",
    "precisely",
    "конкретно",
)

# Reason stamped when an explicit override wins over the heuristic.
_OVERRIDE_REASON: str = "override"


def _clamp_level(level: int, max_level: int) -> int:
    """Clamp ``level`` into the closed community-level range ``[0, max_level]``."""
    if level < 0:
        return 0
    if level > max_level:
        return max_level
    return level


@dataclass(frozen=True)
class LevelChoice:
    """One resolved community-level choice (§11.7).

    ``level`` — the chosen ``community_level`` in ``[0, max_level]``; ``reason`` — a
    short human-readable explanation (``'override'`` when forced); ``breadth_score`` —
    how broad/global the query read, in ``[0, 1]`` (``1`` = maximally global).
    """

    level: int
    reason: str
    breadth_score: float

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "reason": self.reason,
            "breadth_score": self.breadth_score,
        }


def _count_markers(text: str, markers: tuple[str, ...]) -> int:
    """Count how many distinct ``markers`` appear as substrings of ``text``."""
    return sum(1 for marker in markers if marker in text)


def select_level(
    query: str,
    *,
    max_level: int = 2,
    override: int | None = None,
) -> LevelChoice:
    """Pick a GraphRAG ``community_level`` for ``query`` (§11.7).

    An explicit ``override`` wins immediately, clamped to ``[0, max_level]`` with
    ``reason='override'``. Otherwise the query is lowercased and scanned for broad and
    narrow markers: a broad majority selects ``max_level``, a narrow majority selects
    level ``0``, and a tie (including an empty query) selects a mid/default level. The
    ``breadth_score`` in ``[0, 1]`` is ``broad / (broad + narrow)`` marker counts, and
    defaults to ``0.5`` when no markers of either kind are present.
    """
    if override is not None:
        level = _clamp_level(override, max_level)
        return LevelChoice(level=level, reason=_OVERRIDE_REASON, breadth_score=0.5)

    lowered = query.casefold()
    broad = _count_markers(lowered, BROAD_MARKERS)
    narrow = _count_markers(lowered, NARROW_MARKERS)
    total = broad + narrow

    breadth_score = 0.5 if total == 0 else broad / total
    # Guard against any float drift so the score is always a clean member of [0, 1].
    breadth_score = min(1.0, max(0.0, breadth_score))

    mid_level = max_level // 2

    if broad > narrow:
        return LevelChoice(
            level=max_level,
            reason=f"broad markers dominate ({broad} broad vs {narrow} narrow)",
            breadth_score=breadth_score,
        )
    if narrow > broad:
        return LevelChoice(
            level=0,
            reason=f"narrow markers dominate ({narrow} narrow vs {broad} broad)",
            breadth_score=breadth_score,
        )
    return LevelChoice(
        level=mid_level,
        reason="no dominant markers; mid/default level",
        breadth_score=breadth_score,
    )

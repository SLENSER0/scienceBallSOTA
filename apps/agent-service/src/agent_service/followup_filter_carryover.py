"""§13.15 память диалога — перенос фильтров / follow-up filter carryover.

:mod:`followup_resolver` binds a dangling pronoun back to the entity of the previous
turn, but a real multi-turn dialogue also carries over *query filters*. Ask "показать с
min_confidence 0.8 для Al-Cu", then follow up with "а для Fe-C?" — the follow-up drops
``min_confidence`` (and ``verified_only``/``date_from`` …) even though the user plainly
still means them to apply. This module is the filter analogue of the entity carryover.

Pure python (no store / no LLM). :func:`carry_filters` copies each configured filter key
that is present in the *prior* turn but absent from the *current* one, never overriding a
key the current turn already sets, and records which keys were carried (sorted). Inputs
are never mutated. :func:`is_followup_filter_query` is a cheap heuristic — a turn that
names neither ``material`` nor ``property`` looks like a bare follow-up that should
inherit context. Every rule is deterministic and hand-checkable. Bilingual (RU/EN) docs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Filter keys eligible for carryover (порядок не важен / order irrelevant — result sorts).
DEFAULT_CARRY_KEYS: tuple[str, ...] = (
    "min_confidence",
    "verified_only",
    "date_from",
    "material",
    "property",
)


@dataclass(frozen=True)
class CarriedFilters:
    """Result of a filter carryover (§13.15): merged filters + which keys were carried.

    Frozen and orjson-serialisable via :meth:`as_dict`.

    * ``filters`` — the effective filter dict after carryover (current ∪ carried-prior).
    * ``carried_keys`` — keys copied from the prior turn, sorted, deduped.
    """

    filters: dict[str, Any]
    carried_keys: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a stable dict (``carried_keys`` as a list, ``filters`` copied)."""
        return {
            "filters": dict(self.filters),
            "carried_keys": list(self.carried_keys),
        }


def carry_filters(
    current: dict[str, Any],
    prior: dict[str, Any],
    carry_keys: tuple[str, ...] = DEFAULT_CARRY_KEYS,
) -> CarriedFilters:
    """Carry prior-turn filters into a follow-up that omits them (§13.15).

    For each ``key`` in ``carry_keys`` that is **present in ``prior`` but absent from
    ``current``**, copy ``prior[key]`` into the result. A key the current turn already
    sets is never overridden (текущий ход главнее / current turn wins). A key absent in
    both is not added. ``carried_keys`` lists exactly the copied keys, sorted.

    Neither ``current`` nor ``prior`` is mutated — the result holds a fresh dict.
    """
    merged: dict[str, Any] = dict(current)
    carried: list[str] = []
    for key in carry_keys:
        if key in prior and key not in current:
            merged[key] = prior[key]
            carried.append(key)
    return CarriedFilters(filters=merged, carried_keys=tuple(sorted(carried)))


def is_followup_filter_query(current: dict[str, Any]) -> bool:
    """True iff ``current`` names neither ``material`` nor ``property`` (bare follow-up).

    Такой ход выглядит как продолжение — стоит унаследовать контекст / a turn with no
    subject of its own reads as a follow-up that should inherit the prior filters.
    """
    return "material" not in current and "property" not in current

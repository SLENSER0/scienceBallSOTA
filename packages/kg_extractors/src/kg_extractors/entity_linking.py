"""Mention → entity linking against an alias map (§6.19).

Pure-python linker: resolve a surface mention to a canonical ``entity_id`` using
a caller-supplied alias map. Three methods, tried in precedence order:

* ``exact`` — the mention matches an entity's canonical surface (score ``1.0``);
* ``alias`` — the mention matches one of an entity's aliases (score ``0.95``);
* ``fuzzy`` — the mention is a near-miss of some surface at or above a similarity
  threshold (score = rapidfuzz ratio / 100, in ``[threshold, 1.0)``).

Матчинг регистронезависимый (casefold) и не чувствителен к окружающим/двойным
пробелам. Если ни один способ не сработал (в т.ч. пустая карта или пустой
mention) — возвращается ``None`` (§6.19).

Alias map shape::

    {entity_id: {"canonical": str, "aliases": Iterable[str]}}

Only rapidfuzz — no I/O, no other dependency.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz, process

__all__ = [
    "EntityLink",
    "link_mention",
    "link_all",
    "EXACT_SCORE",
    "ALIAS_SCORE",
    "FUZZY_THRESHOLD",
]

Method = Literal["exact", "alias", "fuzzy"]

# Score assigned to a perfect (case-folded) match on an entity's canonical form.
EXACT_SCORE = 1.0
# Aliases are a slightly weaker signal than the canonical surface (§6.19).
ALIAS_SCORE = 0.95
# rapidfuzz ratio (0..100); a fuzzy candidate below this is rejected as a miss.
FUZZY_THRESHOLD = 85.0

# ``entity_id`` lookups by normalized surface: (canonical, alias, fuzzy_pool).
_Index = tuple[dict[str, str], dict[str, str], dict[str, str]]


@dataclass(frozen=True)
class EntityLink:
    """One resolved ``mention → entity`` edge (§6.19).

    Fields
    ------
    surface
        The mention exactly as supplied (original case/spacing preserved).
    entity_id
        Canonical id of the linked entity.
    score
        Confidence in ``[0.0, 1.0]``: ``1.0`` exact, ``0.95`` alias, else the
        rapidfuzz ratio / 100.
    method
        Which strategy matched — ``"exact"`` / ``"alias"`` / ``"fuzzy"``.
    """

    surface: str
    entity_id: str
    score: float
    method: Method

    def as_dict(self) -> dict[str, object]:
        """Full structured view (all fields, JSON-friendly)."""
        return {
            "surface": self.surface,
            "entity_id": self.entity_id,
            "score": self.score,
            "method": self.method,
        }


def _norm(text: object) -> str:
    """Fold a surface for lookup: collapse whitespace + casefold.

    ``"  Red   Ochre "`` → ``"red ochre"`` so matching ignores case and both
    leading/trailing and repeated internal spaces.
    """
    return " ".join(str(text).split()).casefold()


def _build_index(alias_map: Mapping[str, Mapping[str, object]]) -> _Index:
    """Fold an alias map into ``(canonical, alias, fuzzy_pool)`` lookups (§6.19).

    Keys are normalized surfaces, values are ``entity_id``. The fuzzy pool holds
    every surface (canonical + aliases). On a normalized-key clash the first
    entity in iteration order wins, keeping results deterministic.
    """
    canonical: dict[str, str] = {}
    alias: dict[str, str] = {}
    pool: dict[str, str] = {}
    for entity_id, entry in alias_map.items():
        if not isinstance(entry, Mapping):
            continue
        canon = entry.get("canonical")
        if canon:
            key = _norm(canon)
            if key:
                canonical.setdefault(key, entity_id)
                pool.setdefault(key, entity_id)
        aliases = entry.get("aliases") or ()
        if isinstance(aliases, str):
            aliases = (aliases,)
        for raw in aliases:
            key = _norm(raw)
            if not key:
                continue
            alias.setdefault(key, entity_id)
            pool.setdefault(key, entity_id)
    return canonical, alias, pool


def _link(surface: str, index: _Index) -> EntityLink | None:
    """Resolve one normalized ``surface`` against a pre-built ``index`` (§6.19)."""
    key = _norm(surface)
    if not key:
        return None
    canonical, alias, pool = index
    if key in canonical:
        return EntityLink(surface, canonical[key], EXACT_SCORE, "exact")
    if key in alias:
        return EntityLink(surface, alias[key], ALIAS_SCORE, "alias")
    if not pool:
        return None
    match = process.extractOne(key, list(pool), scorer=fuzz.ratio)
    if match is None:
        return None
    cand_key, ratio, _ = match
    if ratio < FUZZY_THRESHOLD:
        return None
    return EntityLink(surface, pool[cand_key], ratio / 100.0, "fuzzy")


def link_mention(surface: str, alias_map: Mapping[str, Mapping[str, object]]) -> EntityLink | None:
    """Link one ``surface`` mention to an entity via ``alias_map`` (§6.19).

    Returns an :class:`EntityLink` (method ``exact`` / ``alias`` / ``fuzzy``) or
    ``None`` when nothing matches — including an empty ``alias_map`` or a blank
    surface. Matching is case- and whitespace-insensitive.
    """
    return _link(surface, _build_index(alias_map))


def link_all(
    mentions: Iterable[str], alias_map: Mapping[str, Mapping[str, object]]
) -> list[EntityLink | None]:
    """Link a batch of mentions positionally (§6.19).

    The alias index is built once, then each mention maps to an
    :class:`EntityLink` or ``None`` (a miss), preserving input order and length
    so ``len(result) == len(list(mentions))``.
    """
    index = _build_index(alias_map)
    return [_link(m, index) for m in mentions]

"""Entity resolution (§8 / §24.3): surface form → canonical taxonomy entity.

Exact match on the RU/EN alias index first, then fuzzy (rapidfuzz). Emits a
match decision (auto_merge / review_needed / separate) by score band (§9.6).
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process

from kg_common.ids import canonical_key
from kg_schema.enums import MatchDecision
from kg_schema.taxonomy import TaxonomyEntry, load_taxonomy

AUTO_MERGE_SCORE = 92.0
REVIEW_SCORE = 80.0


@dataclass
class ResolvedEntity:
    surface: str
    entry: TaxonomyEntry | None
    score: float
    decision: MatchDecision

    @property
    def canonical_id(self) -> str | None:
        return self.entry.node_id if self.entry else None


class EntityResolver:
    def __init__(self) -> None:
        self._idx = load_taxonomy()
        self._keys = self._idx.all_keys()
        self._map = self._idx.keys_to_entries()

    def resolve(self, surface: str, entity_type: str | None = None) -> ResolvedEntity:
        key = canonical_key(surface)
        exact = self._idx.resolve_exact(surface)
        if exact is not None and (entity_type is None or exact.node_type == entity_type):
            return ResolvedEntity(surface, exact, 100.0, MatchDecision.AUTO_MERGE)

        match = process.extractOne(key, self._keys, scorer=fuzz.token_sort_ratio)
        if not match:
            return ResolvedEntity(surface, None, 0.0, MatchDecision.SEPARATE)
        cand_key, score, _ = match
        entry = self._map[cand_key]
        if entity_type and entry.node_type != entity_type:
            score -= 15
        if score >= AUTO_MERGE_SCORE:
            decision = MatchDecision.AUTO_MERGE
        elif score >= REVIEW_SCORE:
            decision = MatchDecision.REVIEW_NEEDED
        else:
            return ResolvedEntity(surface, None, score, MatchDecision.SEPARATE)
        return ResolvedEntity(surface, entry, score, decision)

    def resolve_many(self, surfaces: list[str]) -> list[ResolvedEntity]:
        return [self.resolve(s) for s in surfaces]


_shared: EntityResolver | None = None


def get_resolver() -> EntityResolver:
    global _shared
    if _shared is None:
        _shared = EntityResolver()
    return _shared

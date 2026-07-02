"""Property vocabulary mapping: mention -> canonical property_id (§8.6).

Strategy: (1) exact/alias match against the controlled vocabulary, then
(2) fuzzy fallback (token-set + Jaro-Winkler). Below ``min_sim`` the mention is
flagged ``review_needed`` and a ``schema_change`` event is emitted for a possibly
new term. Unit compatibility against the canonical property's ``allowed_units``
is checked when a unit is supplied (§8.6 integration with units).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from kg_er.comparisons.text import clean_text
from kg_er.store.property_vocab import PropertyVocabulary


@dataclass
class PropertyMapping:
    mention: str
    canonical_id: str | None
    score: float
    status: str  # "mapped" | "review_needed"
    unit_ok: bool = True
    events: list[dict] = field(default_factory=list)


class PropertyMapper:
    def __init__(self, vocab: PropertyVocabulary, *, min_sim: float = 0.82) -> None:
        self.vocab = vocab
        self.min_sim = min_sim

    def _fuzzy_best(self, mention_clean: str) -> tuple[str | None, float]:
        best_id: str | None = None
        best: float = 0.0
        for cid, aliases in self.vocab.alias_index().items():
            for alias in aliases:
                score = fuzz.token_set_ratio(mention_clean, alias) / 100.0
                if score > best:
                    best, best_id = score, cid
        return best_id, best

    def map(self, mention: str, *, unit: str | None = None) -> PropertyMapping:
        cleaned = clean_text(mention)
        exact = self.vocab.lookup_exact(cleaned)
        if exact is not None:
            return PropertyMapping(
                mention=mention,
                canonical_id=exact,
                score=1.0,
                status="mapped",
                unit_ok=self._unit_ok(exact, unit),
            )
        cid, score = self._fuzzy_best(cleaned)
        if cid is not None and score >= self.min_sim:
            return PropertyMapping(
                mention=mention,
                canonical_id=cid,
                score=round(score, 4),
                status="mapped",
                unit_ok=self._unit_ok(cid, unit),
            )
        # below threshold -> flag + schema_change event (§12.2)
        return PropertyMapping(
            mention=mention,
            canonical_id=cid,
            score=round(score, 4),
            status="review_needed",
            events=[
                {
                    "type": "schema_change",
                    "reason": "new_or_ambiguous_property_term",
                    "mention": mention,
                    "nearest": cid,
                    "score": round(score, 4),
                }
            ],
        )

    def _unit_ok(self, canonical_id: str, unit: str | None) -> bool:
        if not unit:
            return True
        allowed = self.vocab.allowed_units(canonical_id)
        if not allowed:
            return True
        return clean_text(unit) in {clean_text(u) for u in allowed}

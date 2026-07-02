"""Decision engine: auto_merge / review_needed / separate (§8.7).

Maps a Splink cluster's match probability to a :class:`MatchDecision` using
per-type thresholds, and turns clusters into merge proposals with a canonical
representative + provenance, honoring reviewed-canonical protection (§8.9).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from kg_er.models.base import ClusterResult
from kg_schema.enums import MatchDecision

_THRESHOLDS_PATH = Path(__file__).with_name("thresholds.yaml")


@lru_cache(maxsize=1)
def _load_thresholds() -> dict[str, dict[str, float]]:
    return yaml.safe_load(_THRESHOLDS_PATH.read_text(encoding="utf-8"))


def thresholds_for(entity_type: str) -> tuple[float, float]:
    """Return (auto_merge, review) thresholds for *entity_type*."""
    cfg = _load_thresholds()
    row = cfg.get(entity_type, cfg["default"])
    return float(row["auto_merge"]), float(row["review"])


def decide(entity_type: str, probability: float) -> MatchDecision:
    auto, review = thresholds_for(entity_type)
    if probability >= auto:
        return MatchDecision.AUTO_MERGE
    if probability >= review:
        return MatchDecision.REVIEW_NEEDED
    return MatchDecision.SEPARATE


@dataclass
class MergeProposal:
    entity_type: str
    members: tuple[str, ...]
    canonical_id: str
    decision: MatchDecision
    probability: float
    blocked_by_review: bool = False

    def as_dict(self) -> dict[str, Any]:  # §9.2 Step 6 output shape
        return {
            "entity_type": self.entity_type,
            "members": list(self.members),
            "canonical_id": self.canonical_id,
            "decision": self.decision.value,
            "match_probability": round(self.probability, 4),
            "blocked_by_review": self.blocked_by_review,
        }


def build_proposals(
    entity_type: str,
    clusters: list[ClusterResult],
    *,
    reviewed_ids: frozenset[str] = frozenset(),
) -> list[MergeProposal]:
    """Turn clusters into merge proposals.

    Singleton clusters (no pair) are SEPARATE. If a cluster contains a
    reviewed/locked canonical id, an AUTO_MERGE is downgraded to REVIEW_NEEDED so
    a human confirms changes to protected canonicals (§8.9).
    """
    proposals: list[MergeProposal] = []
    for c in clusters:
        if len(c.members) < 2:
            continue  # singletons need no decision
        decision = decide(entity_type, c.max_probability)
        canonical = min(c.members)  # deterministic representative
        blocked = bool(reviewed_ids & set(c.members))
        if blocked and decision is MatchDecision.AUTO_MERGE:
            decision = MatchDecision.REVIEW_NEEDED
        proposals.append(
            MergeProposal(
                entity_type=entity_type,
                members=c.members,
                canonical_id=canonical,
                decision=decision,
                probability=c.max_probability,
                blocked_by_review=blocked,
            )
        )
    return proposals

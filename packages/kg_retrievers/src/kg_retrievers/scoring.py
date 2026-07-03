"""Retrieval scoring: evidence-quality, graph-proximity, weighted fusion (§12.4-12.6).

Complements the RRF hybrid retriever with two domain signals and a configurable
weighted fusion:

- **evidence_quality** rewards candidates backed by stronger, verified,
  higher-confidence evidence (peer-reviewed > patent > protocol > report > …).
- **graph_proximity** rewards candidates close (few hops) to the query's seed
  entities in the graph.
- **weighted_fuse** min-max-normalizes each component to [0,1] and combines them
  with configurable weights (default per §12.4).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from kg_retrievers.graph_store import KuzuGraphStore

# Higher = stronger provenance (§3.6). Unknown strengths fall back to 0.3.
STRENGTH_RANK: dict[str, float] = {
    "peer_reviewed": 1.0,
    "patent": 0.8,
    "experiment_protocol": 0.75,
    "standard": 0.7,
    "internal_report": 0.55,
    "conference": 0.5,
    "preprint": 0.45,
    "unverified": 0.3,
}

# §12.4 default fusion weights.
DEFAULT_WEIGHTS: dict[str, float] = {
    "dense": 0.35,
    "keyword": 0.25,
    "graph_proximity": 0.20,
    "evidence_quality": 0.10,
    "recency": 0.10,
}


def recency_score(node: dict[str, Any], *, now_year: int, half_life_years: float = 8.0) -> float:
    """Exponential-decay recency in [0,1] from a node's ``year`` (no year → 0.5)."""
    year = node.get("year")
    if not isinstance(year, (int, float)) or year <= 0:
        return 0.5
    age = max(0.0, now_year - float(year))
    return round(0.5 ** (age / half_life_years), 4)


def evidence_quality_score(node: dict[str, Any]) -> float:
    """Quality in [0,1] from evidence strength × confidence, boosted if verified."""
    strength = STRENGTH_RANK.get(str(node.get("evidence_strength") or "").lower(), 0.3)
    conf = node.get("confidence")
    conf = float(conf) if isinstance(conf, (int, float)) else 0.6
    base = 0.7 * strength + 0.3 * max(0.0, min(1.0, conf))
    if node.get("verified") is True or node.get("review_status") == "accepted":
        base = min(1.0, base + 0.1)
    return round(base, 4)


def _neighbors(store: KuzuGraphStore, node_id: str) -> list[str]:
    rows = store.rows(
        "MATCH (n:Node {id:$id})-[:Rel]-(m:Node) RETURN DISTINCT m.id", {"id": node_id}
    )
    return [r[0] for r in rows]


def graph_proximity_score(
    store: KuzuGraphStore, candidate_id: str, seed_ids: list[str], *, max_hops: int = 3
) -> float:
    """1.0 if candidate is a seed, decaying with hop distance, 0.0 beyond max_hops."""
    seeds = set(seed_ids)
    if not seeds or not candidate_id:
        return 0.0
    if candidate_id in seeds:
        return 1.0
    visited = {candidate_id}
    frontier: deque[tuple[str, int]] = deque([(candidate_id, 0)])
    while frontier:
        nid, dist = frontier.popleft()
        if dist >= max_hops:
            continue
        for nb in _neighbors(store, nid):
            if nb in seeds:
                return round((max_hops - dist) / max_hops, 4)  # closer → higher
            if nb not in visited:
                visited.add(nb)
                frontier.append((nb, dist + 1))
    return 0.0


def _minmax(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    lo, hi = min(scores.values()), max(scores.values())
    if hi <= lo:
        return dict.fromkeys(scores, 1.0)
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


@dataclass
class FusedScore:
    id: str
    score: float
    components: dict[str, float] = field(default_factory=dict)


def weighted_fuse(
    components: dict[str, dict[str, float]], weights: dict[str, float] | None = None
) -> list[FusedScore]:
    """Min-max-normalize each component and combine by weight; ranked desc.

    ``components`` maps a signal name (dense/keyword/graph_proximity/…) to
    ``{candidate_id: raw_score}``. Missing signals for a candidate count as 0.
    """
    w = weights or DEFAULT_WEIGHTS
    norm = {name: _minmax(scores) for name, scores in components.items()}
    ids = {cid for scores in components.values() for cid in scores}
    out: list[FusedScore] = []
    for cid in ids:
        comp = {name: norm[name].get(cid, 0.0) for name in components}
        total = sum(w.get(name, 0.0) * val for name, val in comp.items())
        out.append(FusedScore(id=cid, score=round(total, 6), components=comp))
    out.sort(key=lambda f: f.score, reverse=True)
    return out

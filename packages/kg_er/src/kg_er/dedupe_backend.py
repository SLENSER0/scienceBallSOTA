"""Transparent blocking + scoring dedupe backend (§8.11).

A lightweight, fully deterministic alternative to the Splink path (§8.5) and to
:mod:`kg_er.deterministic`, in the spirit of the classic *dedupe* / *OpenRefine*
recipe: (1) **block** records by a sorted-token key or a first-3-chars prefix key
so only plausibly-matching records are ever compared; (2) **score** each candidate
pair with :func:`rapidfuzz.fuzz.token_set_ratio` plus a same-first-token boost;
(3) **cluster** pairs above a threshold with the same union-find used by the other
backends, so results are drop-in ``ClusterResult`` lists for the decision engine
(§8.7).

The point of blocking is transparency and cost: it makes *why* two records were
(not) compared inspectable, and turns an O(n^2) scan into a handful of within-block
comparisons — see :func:`candidate_pairs` / :func:`blocking_stats`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from rapidfuzz.fuzz import token_set_ratio

from kg_er.comparisons.text import clean_text
from kg_er.models.base import ClusterResult, _union_find

# Default same-first-token boost; per-type overrides let e.g. a shared Person
# family-name or Lab org-token count for more (both share the leading token).
_DEFAULT_BOOST = 0.15
_FIRST_TOKEN_BOOST: dict[str, float] = {
    "Person": 0.20,
    "Lab": 0.10,
    "ResearchTeam": 0.10,
}

_PREFIX_LEN = 3


@dataclass(frozen=True, slots=True)
class BlockingStats:
    """Blocking effectiveness summary (§8.11): how many comparisons it saves."""

    n_rows: int
    n_all_pairs: int
    n_candidate_pairs: int

    @property
    def reduction_ratio(self) -> float:
        """Fraction of the all-pairs comparisons that blocking skips."""
        if self.n_all_pairs == 0:
            return 0.0
        return 1.0 - self.n_candidate_pairs / self.n_all_pairs

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n_rows": self.n_rows,
            "n_all_pairs": self.n_all_pairs,
            "n_candidate_pairs": self.n_candidate_pairs,
            "reduction_ratio": self.reduction_ratio,
        }


def block_key(name: str | None) -> frozenset[str]:
    """Block keys for *name* (§8.11): a sorted-token key and a first-3-chars key.

    Two records are compared iff their key sets intersect, so a shared prefix
    (``"печь взвешенной плавки"`` / ``"печь ПВП"`` → both ``"печ"``) or an
    identical multiset of tokens in any order is enough to co-block them.
    """
    cleaned = clean_text(name)
    if not cleaned:
        return frozenset()
    tokens = cleaned.split()
    sorted_key = " ".join(sorted(tokens))
    prefix_key = cleaned[:_PREFIX_LEN]
    return frozenset({sorted_key, prefix_key})


def similarity(a: str | None, b: str | None, *, boost: float = _DEFAULT_BOOST) -> float:
    """Pairwise name similarity in [0, 1] (§8.11).

    ``token_set_ratio`` (order-independent, robust to abbreviations like
    ``"печь ПВП"``) scaled to [0, 1], plus a *boost* when both names share their
    leading token — the head word carries the most identifying weight.
    """
    ca, cb = clean_text(a), clean_text(b)
    if not ca or not cb:
        return 0.0
    score = token_set_ratio(ca, cb) / 100.0
    ta, tb = ca.split(), cb.split()
    if ta and tb and ta[0] == tb[0]:
        score = min(1.0, score + boost)
    return score


def _row_name(row: dict[str, Any]) -> str:
    """Prefer a precomputed ``name_clean`` column, else clean ``name``."""
    return clean_text(row.get("name_clean") or row.get("name"))


def candidate_pairs(rows: Sequence[dict[str, Any]]) -> list[tuple[str, str]]:
    """Blocked candidate id-pairs (§8.11): only within-block comparisons.

    Returns a sorted, de-duplicated list of ``(id_a, id_b)`` with ``id_a <= id_b``.
    Its length vs ``n*(n-1)/2`` is exactly how much blocking prunes.
    """
    buckets: dict[str, list[str]] = {}
    for row in rows:
        uid = str(row["unique_id"])
        for key in block_key(_row_name(row)):
            buckets.setdefault(key, []).append(uid)

    pairs: set[tuple[str, str]] = set()
    for uids in buckets.values():
        for i in range(len(uids)):
            for j in range(i + 1, len(uids)):
                a, b = uids[i], uids[j]
                pairs.add((a, b) if a <= b else (b, a))
    return sorted(pairs)


def blocking_stats(rows: Sequence[dict[str, Any]]) -> BlockingStats:
    """Compare blocked candidate count against the full O(n^2) pair count (§8.11)."""
    n = len(rows)
    all_pairs = n * (n - 1) // 2
    return BlockingStats(n, all_pairs, len(candidate_pairs(rows)))


def dedupe_clusters(
    entity_type: str, rows: Sequence[dict[str, Any]], *, threshold: float = 0.55
) -> list[ClusterResult]:
    """Block, score, and union-find candidate pairs into clusters (§8.11).

    *entity_type* selects the same-first-token boost weight; scoring is otherwise
    name-centric, so this backend is a transparent cross-check on the feature-based
    :func:`kg_er.deterministic.deterministic_clusters`. Every input id appears in
    exactly one returned cluster (singletons included).
    """
    boost = _FIRST_TOKEN_BOOST.get(entity_type, _DEFAULT_BOOST)
    name_by_id = {str(r["unique_id"]): _row_name(r) for r in rows}

    pairs: list[tuple[str, str]] = []
    pair_prob: dict[tuple[str, str], float] = {}
    for a, b in candidate_pairs(rows):
        score = similarity(name_by_id[a], name_by_id[b], boost=boost)
        if score >= threshold:
            pairs.append((a, b))
            pair_prob[(a, b)] = score

    parent = _union_find(pairs)
    # Represent singletons so callers see every input id exactly once.
    for uid in name_by_id:
        parent.setdefault(uid, uid)

    groups: dict[str, set[str]] = {}
    for node in parent:
        root = node
        while parent[root] != root:
            root = parent[root]
        groups.setdefault(root, set()).add(node)

    clusters: list[ClusterResult] = []
    for members in groups.values():
        member_tuple = tuple(sorted(members))
        rel = {k: v for k, v in pair_prob.items() if k[0] in members and k[1] in members}
        clusters.append(
            ClusterResult(
                members=member_tuple,
                max_probability=max(rel.values()) if rel else 0.0,
                pair_probabilities=rel,
            )
        )
    return clusters

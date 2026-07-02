"""Splink-lite entity resolution (§8.5–8.9): blocking → pairwise scoring → clusters.

A deterministic, dependency-light alternative to Splink for merging duplicate
surface forms (materials, methods, cross-lingual aliases). The pipeline is:

* §8.5 ``blocking`` — generate candidate pairs sharing a token/prefix block key,
  so we never score the full O(n²) cartesian product.
* §8.6/§8.7 ``score_pair`` — blend rapidfuzz ``token_sort_ratio`` with the Jaro
  similarity over the cross product of every record's terms (name + aliases).
* §8.8 union-find over the *auto* pairs collapses transitive duplicates into
  clusters (a → b, b → c ⇒ {a, b, c}).
* §8.9 each cluster gets a ``MatchDecision`` (auto_merge / review_needed /
  separate) from the score bands.

Everything is deterministic: inputs are processed in sorted order and scores are
rounded, so the same records always yield the same clusters.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from rapidfuzz import fuzz
from rapidfuzz.distance import Jaro

from kg_schema.enums import MatchDecision

Record = Mapping[str, object]

#: Blend weights for ``score_pair`` (token order robustness + char-level Jaro).
TOKEN_SORT_WEIGHT = 0.5
JARO_WEIGHT = 0.5
#: Prefix length used to derive block keys from tokens (§8.5).
PREFIX_LEN = 4
#: Default score bands (§8.9); overridable per ``resolve_records`` call.
AUTO_MERGE = 0.9
REVIEW = 0.75

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _terms(record: Record) -> list[str]:
    """Name + aliases of a record, de-duplicated, order-preserving."""
    out: list[str] = []
    seen: set[str] = set()
    name = record.get("name")
    aliases = record.get("aliases") or []
    values: list[object] = [name, *aliases] if isinstance(aliases, Sequence) else [name]
    for value in values:
        if not value:
            continue
        text = str(value).strip()
        low = text.lower()
        if text and low not in seen:
            seen.add(low)
            out.append(text)
    return out


def _tokens(text: str) -> set[str]:
    """Unicode word tokens (Latin + Cyrillic), lowercased, length ≥ 2."""
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= 2}


def _block_keys(record: Record) -> frozenset[str]:
    """Block keys for a record: each token plus its ``PREFIX_LEN`` prefix (§8.5)."""
    keys: set[str] = set()
    for term in _terms(record):
        for tok in _tokens(term):
            keys.add(tok)
            keys.add(tok[:PREFIX_LEN])
    return frozenset(keys)


def blocking(records: Sequence[Record]) -> list[tuple[int, int]]:
    """Candidate index pairs ``(i, j)`` with ``i < j`` sharing a block key (§8.5).

    Deterministic: the returned list is sorted. Records with no shared token or
    prefix are never compared downstream.
    """
    key_to_ids: dict[str, list[int]] = {}
    for idx, rec in enumerate(records):
        for key in _block_keys(rec):
            key_to_ids.setdefault(key, []).append(idx)
    pairs: set[tuple[int, int]] = set()
    for ids in key_to_ids.values():
        if len(ids) < 2:
            continue
        for a_i in range(len(ids)):
            for b_i in range(a_i + 1, len(ids)):
                lo, hi = sorted((ids[a_i], ids[b_i]))
                if lo != hi:
                    pairs.add((lo, hi))
    return sorted(pairs)


def _sim(x: str, y: str) -> float:
    """Blended token_sort + Jaro similarity of two strings in ``[0, 1]``."""
    token_sort = fuzz.token_sort_ratio(x, y) / 100.0
    jaro = Jaro.normalized_similarity(x, y)
    return TOKEN_SORT_WEIGHT * token_sort + JARO_WEIGHT * jaro


def score_pair(a: Record, b: Record) -> float:
    """Best blended similarity over the cross product of both records' terms (§8.6/§8.7).

    Considers every ``name``/``alias`` of ``a`` against every one of ``b`` so a
    shared cross-lingual alias (e.g. ``"обратный осмос"``) yields a perfect match
    even when the canonical names differ. Returns a value in ``[0, 1]`` rounded
    for determinism.
    """
    a_terms = [t.lower() for t in _terms(a)]
    b_terms = [t.lower() for t in _terms(b)]
    if not a_terms or not b_terms:
        return 0.0
    best = max(_sim(ta, tb) for ta in a_terms for tb in b_terms)
    return round(best, 6)


class _UnionFind:
    """Minimal union-find over integer record indices (§8.8)."""

    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, x: int) -> int:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self._parent[max(rx, ry)] = min(rx, ry)


@dataclass
class Cluster:
    """A resolved group of records with a merge decision (§8.9)."""

    members: tuple[int, ...]
    names: tuple[str, ...]
    decision: MatchDecision
    score: float = 0.0
    review_links: tuple[int, ...] = field(default_factory=tuple)


def resolve_records(
    records: Sequence[Record],
    auto: float = AUTO_MERGE,
    review: float = REVIEW,
) -> list[Cluster]:
    """Resolve records into clusters with a ``MatchDecision`` (§8.5–8.9).

    Blocks, scores candidate pairs, then union-finds the *auto* pairs
    (``score >= auto``) into clusters. A multi-record cluster is ``auto_merge``.
    A singleton touched by a *review* pair (``review <= score < auto``) is
    ``review_needed``; otherwise ``separate``. Deterministic for fixed inputs.
    """
    n = len(records)
    uf = _UnionFind(n)
    auto_score: dict[tuple[int, int], float] = {}
    review_score: dict[tuple[int, int], float] = {}
    for i, j in blocking(records):
        s = score_pair(records[i], records[j])
        if s >= auto:
            auto_score[(i, j)] = s
            uf.union(i, j)
        elif s >= review:
            review_score[(i, j)] = s

    groups: dict[int, list[int]] = {}
    for idx in range(n):
        groups.setdefault(uf.find(idx), []).append(idx)

    clusters: list[Cluster] = []
    for members in sorted(groups.values(), key=lambda m: m[0]):
        member_set = set(members)
        internal_auto = [
            sc for (i, j), sc in auto_score.items() if i in member_set and j in member_set
        ]
        if len(members) > 1:
            decision = MatchDecision.AUTO_MERGE
            best = round(max(internal_auto), 6) if internal_auto else 0.0
            links: tuple[int, ...] = ()
        else:
            (single,) = members
            touching = {
                (other, sc)
                for (i, j), sc in review_score.items()
                for other in (j if i == single else i,)
                if single in (i, j)
            }
            if touching:
                decision = MatchDecision.REVIEW_NEEDED
                best = round(max(sc for _, sc in touching), 6)
                links = tuple(sorted(other for other, _ in touching))
            else:
                decision = MatchDecision.SEPARATE
                best = 0.0
                links = ()
        names = tuple(str(records[m].get("name") or "") for m in members)
        clusters.append(Cluster(tuple(members), names, decision, best, links))
    return clusters

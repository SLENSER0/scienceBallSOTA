"""Candidate reranker: MMR diversity + evidence boost (§12.9).

A lightweight, cross-encoder-free reranker that reorders retrieval candidates
without any learned model or extra dependency:

- :func:`mmr_rerank` — **Maximal Marginal Relevance** («максимальная маргинальная
  релевантность»). Trades relevance against redundancy so the result set is
  *diverse* («разнообразие»): each pick maximizes
  ``lambda_ * relevance - (1 - lambda_) * max_similarity_to_already_picked``.
  Redundancy («избыточность») is a Jaccard overlap over the candidate's token
  set (derived from its ``text``). ``lambda_ = 1.0`` collapses to pure relevance
  order; lower ``lambda_`` pushes near-duplicates down.
- :func:`evidence_boost_rerank` — nudges («усиление по качеству доказательств»)
  ranking by an evidence-quality signal, reusing
  :func:`kg_retrievers.scoring.evidence_quality_score` so the notion of "stronger
  evidence" stays in lock-step with the fusion scorer (§12.5).

Candidates are dicts like ``{"id", "score", "text"?, "node"?}``. Both functions
return a list of frozen :class:`RerankedItem` (with :meth:`~RerankedItem.as_dict`),
preserving ids. Pure python — no numpy, no external reranker.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from kg_retrievers.scoring import evidence_quality_score

# Tokenizer keeps latin + cyrillic word characters; everything else splits (RU/EN).
_TOKEN_RE = re.compile(r"[^0-9a-zA-Zа-яА-ЯёЁ]+")


@dataclass(frozen=True)
class RerankedItem:
    """One reranked candidate with provenance of *why* it landed here (§12.9).

    ``score`` is the rerank score used for ordering (the MMR marginal value or the
    boosted relevance); ``base_score`` is the candidate's original relevance so a
    caller can see the delta. ``rank`` is the final 0-based position.
    """

    id: str
    score: float
    base_score: float
    rank: int
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "score": self.score,
            "base_score": self.base_score,
            "rank": self.rank,
            "reason": self.reason,
        }


def _score_of(cand: Mapping[str, Any]) -> float:
    """Extract the candidate's relevance score, defaulting to 0.0 if absent/bad."""
    val = cand.get("score", 0.0)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _text_of(cand: Mapping[str, Any]) -> str:
    text = cand.get("text")
    return text if isinstance(text, str) else ""


def _node_of(cand: Mapping[str, Any]) -> Mapping[str, Any]:
    """Evidence carrier: the nested ``node`` if present, else the candidate itself."""
    node = cand.get("node")
    return node if isinstance(node, Mapping) else cand


def _tokenize(text: str) -> frozenset[str]:
    """Lower-cased word-token set for Jaccard redundancy (empty text → empty set)."""
    if not text:
        return frozenset()
    return frozenset(tok for tok in _TOKEN_RE.split(text.lower()) if tok)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity |a∩b|/|a∪b| in [0,1]; 0.0 if either side is empty."""
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _normalized_relevance(scores: list[float]) -> list[float]:
    """Map raw relevance into [0,1] so ``lambda_`` balances against Jaccard.

    Max-normalization (``s / max``) is used when the top score is positive: it keeps
    the *proportions* between candidates and pins the best at 1.0. If all scores are
    non-positive it falls back to a min-max shift; a degenerate all-equal set maps to
    all-1.0 (relevance carries no signal, redundancy decides).
    """
    if not scores:
        return []
    hi = max(scores)
    if hi > 0:
        return [s / hi for s in scores]
    lo = min(scores)
    span = hi - lo
    if span <= 0:
        return [1.0] * len(scores)
    return [(s - lo) / span for s in scores]


def mmr_rerank(
    candidates: Iterable[Mapping[str, Any]],
    *,
    lambda_: float = 0.7,
    k: int | None = None,
) -> list[RerankedItem]:
    """Rerank ``candidates`` by Maximal Marginal Relevance (§12.9).

    Greedily selects, at each step, the candidate maximizing::

        lambda_ * relevance - (1 - lambda_) * max Jaccard(text, already_selected)

    Relevance is max-normalized to [0,1] (see :func:`_normalized_relevance`).
    ``lambda_ = 1.0`` reduces to pure relevance order; smaller ``lambda_`` demotes
    near-duplicates. ``k`` truncates to the top-k selections (``None`` → all).
    Ids are preserved; ties break toward higher relevance then earlier input order.
    """
    items = list(candidates)
    n = len(items)
    if n == 0:
        return []
    lam = float(lambda_)
    rel = _normalized_relevance([_score_of(c) for c in items])
    toks = [_tokenize(_text_of(c)) for c in items]
    # Stable candidate order: highest relevance first, then original index. This makes
    # the lambda_=1.0 case fall out as an exact relevance-descending ranking.
    order = sorted(range(n), key=lambda i: (-rel[i], i))
    limit = n if k is None else max(0, min(int(k), n))

    selected: list[int] = []
    chosen: set[int] = set()
    out: list[RerankedItem] = []
    while len(selected) < limit:
        best_i: int | None = None
        best_mmr = float("-inf")
        for i in order:
            if i in chosen:
                continue
            redundancy = max((_jaccard(toks[i], toks[j]) for j in selected), default=0.0)
            mmr = lam * rel[i] - (1.0 - lam) * redundancy
            if mmr > best_mmr:
                best_mmr = mmr
                best_i = i
        assert best_i is not None  # limit <= n guarantees a remaining candidate
        selected.append(best_i)
        chosen.add(best_i)
        cand = items[best_i]
        out.append(
            RerankedItem(
                id=str(cand.get("id")),
                score=round(best_mmr, 6),
                base_score=round(_score_of(cand), 6),
                rank=len(selected) - 1,
                reason="mmr",
            )
        )
    return out


def evidence_boost_rerank(
    candidates: Iterable[Mapping[str, Any]],
    *,
    weight: float = 0.2,
) -> list[RerankedItem]:
    """Rerank ``candidates`` by relevance nudged with evidence quality (§12.9).

    New score = ``base_score + weight * evidence_quality_score(node)``, reusing the
    fusion scorer's :func:`~kg_retrievers.scoring.evidence_quality_score` on each
    candidate's ``node`` (or the candidate itself if it has no nested node). A larger
    ``weight`` lets high-evidence-quality candidates overtake marginally-more-relevant
    but weakly-supported ones. ``weight = 0.0`` leaves the relevance order untouched.
    Ids are preserved; ties break toward earlier input order.
    """
    items = list(candidates)
    if not items:
        return []
    w = float(weight)
    ranked = []
    for idx, cand in enumerate(items):
        base = _score_of(cand)
        eq = evidence_quality_score(_node_of(cand))
        ranked.append((idx, cand, base, eq, base + w * eq))
    ranked.sort(key=lambda t: (-t[4], t[0]))  # boosted desc, then stable by input order
    return [
        RerankedItem(
            id=str(cand.get("id")),
            score=round(boosted, 6),
            base_score=round(base, 6),
            rank=rank,
            reason=f"evidence_boost:eq={round(eq, 4)}",
        )
        for rank, (_idx, cand, base, eq, boosted) in enumerate(ranked)
    ]

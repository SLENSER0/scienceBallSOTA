"""Retrieval eval metrics — recall@k / precision@k / hit@k / MRR / nDCG / AP (§18.6/§18.7).

Pure, deterministic, numpy-free ranking metrics for scoring a retriever's ranked
list of predicted ids (evidence chunks / experiments) against a golden set of
relevant ids (§15.2: ``Recall@10`` для evidence, ``MRR`` для релевантных
экспериментов, ``nDCG``/``hit@k`` для hybrid vs single-mode сравнений).

Each metric takes a ranked ``predicted`` iterable (best-first) plus the set of
``relevant`` golden ids. Binary relevance is assumed (an id is либо relevant,
либо нет). Duplicate ids in the ranked list are collapsed to their first
occurrence so a chunk retrieved by several hybrid retrievers is not double
counted. Values are deterministic — the same inputs always yield the same числа.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Iterable
from dataclasses import dataclass

DEFAULT_K = 10


def _unique(ranked: Iterable[Hashable]) -> list[Hashable]:
    """Materialize ``ranked`` keeping first occurrence order, dropping duplicates."""
    seen: set[Hashable] = set()
    out: list[Hashable] = []
    for item in ranked:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _top_k(ranked: Iterable[Hashable], k: int) -> list[Hashable]:
    """Deduplicated top-``k`` prefix; empty when ``k <= 0``."""
    return _unique(ranked)[:k] if k > 0 else []


def recall_at_k(
    ranked: Iterable[Hashable], relevant: Iterable[Hashable], k: int = DEFAULT_K
) -> float:
    """Fraction of relevant ids present in the top-``k`` (denominator = |relevant|).

    Empty golden set is vacuously complete → ``1.0`` (matches ``gap_metrics.prf``).
    """
    rel = set(relevant)
    if not rel:
        return 1.0
    hits = sum(1 for item in _top_k(ranked, k) if item in rel)
    return hits / len(rel)


def precision_at_k(
    ranked: Iterable[Hashable], relevant: Iterable[Hashable], k: int = DEFAULT_K
) -> float:
    """Fraction of the top-``k`` predictions that are relevant.

    Denominator is ``min(k, #retrieved)`` so returning fewer than ``k`` results is
    not penalised when every returned id is relevant. Empty prefix → ``0.0``.
    """
    top = _top_k(ranked, k)
    if not top:
        return 0.0
    hits = sum(1 for item in top if item in set(relevant))
    return hits / len(top)


def hit_at_k(ranked: Iterable[Hashable], relevant: Iterable[Hashable], k: int = DEFAULT_K) -> float:
    """``1.0`` if at least one relevant id is in the top-``k`` else ``0.0`` (success@k)."""
    rel = set(relevant)
    return 1.0 if any(item in rel for item in _top_k(ranked, k)) else 0.0


def mrr(ranked: Iterable[Hashable], relevant: Iterable[Hashable]) -> float:
    """Reciprocal rank of the first relevant id (1-indexed); ``0.0`` if none found.

    Per-query value; the *mean* reciprocal rank over many queries is obtained via
    :func:`aggregate` (§15.2 MRR для релевантных экспериментов).
    """
    rel = set(relevant)
    for position, item in enumerate(_unique(ranked), start=1):
        if item in rel:
            return 1.0 / position
    return 0.0


def ndcg_at_k(
    ranked: Iterable[Hashable], relevant: Iterable[Hashable], k: int = DEFAULT_K
) -> float:
    """Normalized DCG@k with binary gains and ``log2(rank + 1)`` discount.

    IDCG is the DCG of the ideal ranking (all relevant ids first). Empty golden
    set or zero IDCG → ``0.0``.
    """
    rel = set(relevant)
    if not rel:
        return 0.0
    top = _top_k(ranked, k)
    dcg = sum(1.0 / math.log2(pos + 1) for pos, item in enumerate(top, start=1) if item in rel)
    ideal_hits = min(len(rel), k) if k > 0 else 0
    idcg = sum(1.0 / math.log2(pos + 1) for pos in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0


def average_precision(ranked: Iterable[Hashable], relevant: Iterable[Hashable]) -> float:
    """Average precision over the full ranking (area under precision-recall).

    Mean of precision taken at each relevant hit position, divided by the total
    number of relevant ids (unretrieved relevants contribute ``0``). The mean of
    this over queries is MAP (via :func:`aggregate`). Empty golden set → ``0.0``.
    """
    rel = set(relevant)
    if not rel:
        return 0.0
    hits = 0
    score = 0.0
    for position, item in enumerate(_unique(ranked), start=1):
        if item in rel:
            hits += 1
            score += hits / position
    return score / len(rel)


@dataclass(frozen=True)
class RetrievalMetrics:
    """Bundle of ranking metrics at a fixed cutoff ``k`` (§18.6/§15.2)."""

    k: int
    recall_at_k: float
    precision_at_k: float
    hit_at_k: float
    mrr: float
    ndcg_at_k: float
    average_precision: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "k": self.k,
            "recall_at_k": round(self.recall_at_k, 4),
            "precision_at_k": round(self.precision_at_k, 4),
            "hit_at_k": round(self.hit_at_k, 4),
            "mrr": round(self.mrr, 4),
            "ndcg_at_k": round(self.ndcg_at_k, 4),
            "average_precision": round(self.average_precision, 4),
        }


def evaluate(
    ranked: Iterable[Hashable], relevant: Iterable[Hashable], k: int = DEFAULT_K
) -> RetrievalMetrics:
    """Compute all ranking metrics for one query at cutoff ``k``."""
    items = _unique(ranked)  # materialize once (safe for generators)
    rel = set(relevant)
    return RetrievalMetrics(
        k=k,
        recall_at_k=recall_at_k(items, rel, k),
        precision_at_k=precision_at_k(items, rel, k),
        hit_at_k=hit_at_k(items, rel, k),
        mrr=mrr(items, rel),
        ndcg_at_k=ndcg_at_k(items, rel, k),
        average_precision=average_precision(items, rel),
    )


def _mean(values: Iterable[float]) -> float:
    vals = list(values)
    return sum(vals) / len(vals) if vals else 0.0


def aggregate(
    runs: Iterable[tuple[Iterable[Hashable], Iterable[Hashable]]], k: int = DEFAULT_K
) -> RetrievalMetrics:
    """Mean of each metric over many queries (§15.2 macro-average).

    ``runs`` is an iterable of ``(ranked, relevant)`` pairs. The mean of
    ``average_precision`` is MAP and the mean of ``mrr`` is the corpus MRR.
    Empty ``runs`` yields all-zero metrics.
    """
    results = [evaluate(ranked, relevant, k) for ranked, relevant in runs]
    return RetrievalMetrics(
        k=k,
        recall_at_k=_mean(r.recall_at_k for r in results),
        precision_at_k=_mean(r.precision_at_k for r in results),
        hit_at_k=_mean(r.hit_at_k for r in results),
        mrr=_mean(r.mrr for r in results),
        ndcg_at_k=_mean(r.ndcg_at_k for r in results),
        average_precision=_mean(r.average_precision for r in results),
    )

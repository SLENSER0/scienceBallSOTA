"""Result diversification over final hits (§12.12).

Финальный шаг ранжирования: не даём одному источнику «забить» выдачу. Two pure-python
diversifiers over an already-scored hit list (each hit — a plain dict with a ``score``
field plus one or more key fields):

- :func:`diversify` — **source-cap** («ограничение по источнику»): caps how many hits
  may share the same source key (``doc_id`` / ``entity`` …) so a single document cannot
  dominate the page. Otherwise the score order is preserved, then the result is truncated
  to ``top_n``. Deterministic, stable on ties.
- :func:`mmr_diversity` — **Maximal Marginal Relevance** («максимальная маргинальная
  релевантность»): reorders trading relevance against *novelty* («новизна») computed from
  a provided similarity key. Each pick maximizes
  ``lambda_ * relevance - (1 - lambda_) * max_similarity_to_already_picked``. Similarity is
  a Jaccard overlap of the hit's similarity-key features (a scalar counts as a one-element
  set). ``lambda_ = 1.0`` collapses to pure relevance order; lower ``lambda_`` promotes
  novel, less-redundant hits.
- :func:`summarize_diversity` — explainability companion returning a frozen
  :class:`DiversityStats` (with :meth:`~DiversityStats.as_dict`) for UI/debug.

Pure python — no numpy, no store/graph access. Callers assemble the scored hit dicts.
Kuzu note: custom node props are not queryable columns — callers RETURN base columns and
read the rest via ``get_node()`` before building the hit dicts fed here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

# Sentinel label for a hit whose source key is missing/None (grouped in stats only).
_NO_KEY = "__nokey__"


def _score_of(hit: Mapping[str, Any]) -> float:
    """Extract a hit's relevance score, defaulting to 0.0 if absent/non-numeric."""
    val = hit.get("score", 0.0)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _features(hit: Mapping[str, Any], sim_key: str) -> frozenset[Any]:
    """Similarity-key feature set of a hit for Jaccard novelty (§12.12).

    A collection value (list/tuple/set/frozenset) becomes its element set; any other
    scalar (str/int/…) becomes a one-element set, so equality acts as similarity 1.0.
    Missing/``None`` → empty set (maximally novel vs everything).
    """
    val = hit.get(sim_key)
    if val is None:
        return frozenset()
    if isinstance(val, (list, tuple, set, frozenset)):
        return frozenset(val)
    return frozenset({val})


def _jaccard(a: frozenset[Any], b: frozenset[Any]) -> float:
    """Jaccard similarity |a∩b|/|a∪b| in [0,1]; 0.0 if either side is empty."""
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _normalized_relevance(scores: list[float]) -> list[float]:
    """Map raw relevance into [0,1] so ``lambda_`` balances against Jaccard (§12.12).

    Max-normalization (``s / max``) when the top score is positive keeps the proportions
    between hits and pins the best at 1.0 (order-preserving → ``lambda_=1.0`` reproduces
    pure relevance order). Non-positive tops fall back to a min-max shift; a degenerate
    all-equal set maps to all-1.0 (relevance carries no signal, novelty decides).
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


@dataclass(frozen=True)
class DiversityStats:
    """Explainability summary of a diversification pass (§12.12).

    ``total_in`` / ``total_out`` are the hit counts before/after; ``dropped`` is how many
    were removed (by the source cap and/or ``top_n`` truncation). ``per_key`` counts the
    surviving hits per source key so a caller can see the cap took effect.
    """

    total_in: int
    total_out: int
    dropped: int
    per_key: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_in": self.total_in,
            "total_out": self.total_out,
            "dropped": self.dropped,
            "per_key": dict(self.per_key),
        }


def _key_label(hit: Mapping[str, Any], key: str) -> str:
    """Stringified source-key label for stats (missing/None → ``_NO_KEY``)."""
    val = hit.get(key)
    return _NO_KEY if val is None else str(val)


def diversify(
    hits: Iterable[Mapping[str, Any]],
    *,
    key: str = "doc_id",
    max_per_key: int = 2,
    top_n: int | None = 20,
) -> list[dict[str, Any]]:
    """Source-cap diversification over final hits (§12.12).

    Sorts ``hits`` by descending ``score`` (stable — ties keep input order), then keeps a
    hit only while its source ``key`` value has appeared fewer than ``max_per_key`` times,
    so one document/entity cannot dominate. The surviving list stays in score order and is
    truncated to ``top_n`` (``None`` → unlimited). Hits are returned as plain dicts (copies
    of the input mappings). Empty input → ``[]``.

    A hit whose ``key`` is missing/``None`` is given a unique bucket, so it is never dropped
    by the cap (we cannot attribute it to a dominating source).
    """
    items = list(hits)
    if not items:
        return []
    cap = int(max_per_key)
    order = sorted(range(len(items)), key=lambda i: (-_score_of(items[i]), i))
    counts: dict[Any, int] = {}
    kept: list[dict[str, Any]] = []
    for idx in order:
        hit = items[idx]
        val = hit.get(key)
        bucket: Any = (_NO_KEY, idx) if val is None else val  # None → unique, never capped
        if counts.get(bucket, 0) >= cap:
            continue
        counts[bucket] = counts.get(bucket, 0) + 1
        kept.append(dict(hit))
        if top_n is not None and len(kept) >= int(top_n):
            break
    return kept


def mmr_diversity(
    hits: Iterable[Mapping[str, Any]],
    *,
    lambda_: float = 0.7,
    sim_key: str = "cluster",
) -> list[dict[str, Any]]:
    """MMR-style relevance/novelty reorder over final hits (§12.12).

    Greedily selects, at each step, the hit maximizing::

        lambda_ * relevance - (1 - lambda_) * max Jaccard(features, already_selected)

    Relevance is max-normalized to [0,1] (see :func:`_normalized_relevance`); features come
    from each hit's ``sim_key`` (see :func:`_features`). ``lambda_ = 1.0`` reduces to pure
    relevance order; smaller ``lambda_`` promotes novel (less-redundant) hits above slightly
    more-relevant near-duplicates. All hits are returned (reordered) as plain dicts; ties
    break toward higher relevance then earlier input order. Empty input → ``[]``.
    """
    items = list(hits)
    n = len(items)
    if n == 0:
        return []
    lam = float(lambda_)
    rel = _normalized_relevance([_score_of(h) for h in items])
    feats = [_features(h, sim_key) for h in items]
    # Stable candidate order: highest relevance first, then original index — makes the
    # lambda_=1.0 case fall out as an exact relevance-descending ordering.
    order = sorted(range(n), key=lambda i: (-rel[i], i))

    selected: list[int] = []
    chosen: set[int] = set()
    while len(selected) < n:
        best_i: int | None = None
        best_mmr = float("-inf")
        for i in order:
            if i in chosen:
                continue
            redundancy = max((_jaccard(feats[i], feats[j]) for j in selected), default=0.0)
            mmr = lam * rel[i] - (1.0 - lam) * redundancy
            if mmr > best_mmr:
                best_mmr = mmr
                best_i = i
        assert best_i is not None  # len(selected) < n guarantees a remaining candidate
        selected.append(best_i)
        chosen.add(best_i)
    return [dict(items[i]) for i in selected]


def summarize_diversity(
    before: Iterable[Mapping[str, Any]],
    after: Iterable[Mapping[str, Any]],
    *,
    key: str = "doc_id",
) -> DiversityStats:
    """Summarize a diversification pass into a frozen :class:`DiversityStats` (§12.12).

    ``before`` / ``after`` are the input and diversified hit lists; ``per_key`` counts the
    surviving hits per source ``key`` (missing/``None`` grouped under ``__nokey__``).
    """
    before_list = list(before)
    after_list = list(after)
    per_key: dict[str, int] = {}
    for hit in after_list:
        label = _key_label(hit, key)
        per_key[label] = per_key.get(label, 0) + 1
    return DiversityStats(
        total_in=len(before_list),
        total_out=len(after_list),
        dropped=len(before_list) - len(after_list),
        per_key=per_key,
    )

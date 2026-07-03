"""Rerank entrypoint with span / confidence penalties + on-off flag (§12.9).

The fusion stage (§12.4-12.6) produces a ranked list of *hits*. Before a hit is
shown or handed to the answer synthesizer, §12.9 asks for a final **rerank pass**
(«переранжирование») that demotes evidentially-weak candidates:

* **missing-source-span penalty** (штраф за отсутствие текстовой привязки) — a hit
  that cannot point at the span of source text it was extracted from is less
  trustworthy than an otherwise-equal hit that can, so it drops below it;
* **low-confidence penalty** (штраф за низкую уверенность) — a hit whose
  ``confidence`` falls *strictly* below a threshold is demoted.

Both penalties are **subtractive** on the fusion ``score``: the adjusted score is
``score - span_penalty - confidence_penalty``. Final ordering is delegated to the
existing :func:`kg_retrievers.rerank.evidence_boost_rerank` primitive (with a zero
evidence weight it is a stable, deterministic sort by the adjusted score, ties
broken toward earlier input order) so this module never re-implements ranking.

The **on-off flag** ``enabled`` makes the pass opt-out: ``enabled=False`` is a
deterministic *passthrough* («сквозной проход») that returns the input fusion
order unchanged, only truncated to ``top_n`` — no penalties, no reordering.

A *hit* is a ``dict`` **or** an object exposing ``score`` (fusion relevance),
``has_span`` (bool) and/or ``span`` (the span itself), ``confidence`` and
``evidence_count``. Fields are read leniently: :func:`rerank` returns the original
hit objects reordered (identity preserved), while :func:`rerank_scored` returns
frozen :class:`HitScore` rows exposing the full penalty breakdown for auditing.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from kg_retrievers.rerank import evidence_boost_rerank

__all__ = [
    "HitScore",
    "rerank",
    "rerank_scored",
    "DEFAULT_TOP_N",
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "MISSING_SPAN_PENALTY",
    "LOW_CONFIDENCE_PENALTY",
]

# §12.9 defaults. Penalties are subtractive on the fusion score; the span penalty
# is larger than the confidence penalty because an unattributable hit is a harder
# provenance failure than a merely low-confidence one.
DEFAULT_TOP_N: int = 50
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.5
MISSING_SPAN_PENALTY: float = 0.5
LOW_CONFIDENCE_PENALTY: float = 0.3


@dataclass(frozen=True)
class HitScore:
    """One hit's rerank breakdown: base fusion score minus penalties (§12.9).

    ``adjusted_score = base_score - span_penalty - confidence_penalty`` is the
    value ordering is based on; ``rank`` is the final 0-based position. On a
    passthrough (``enabled=False``) both penalties are ``0.0`` and
    ``adjusted_score == base_score``.
    """

    id: str | None
    base_score: float
    adjusted_score: float
    span_penalty: float
    confidence_penalty: float
    has_span: bool
    confidence: float | None
    evidence_count: int
    rank: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "base_score": self.base_score,
            "adjusted_score": self.adjusted_score,
            "span_penalty": self.span_penalty,
            "confidence_penalty": self.confidence_penalty,
            "has_span": self.has_span,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "rank": self.rank,
        }


def _get(hit: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a hit that may be a ``Mapping`` or a plain object."""
    if isinstance(hit, Mapping):
        return hit.get(key, default)
    return getattr(hit, key, default)


def _id_of(hit: Any) -> str | None:
    val = _get(hit, "id", None)
    return str(val) if val is not None else None


def _score_of(hit: Any) -> float:
    """Fusion relevance of a hit, defaulting to 0.0 if absent/non-numeric."""
    val = _get(hit, "score", 0.0)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _has_span(hit: Any) -> bool:
    """True if the hit carries a source span (explicit ``has_span`` wins).

    Falls back to the truthiness of ``span`` so a hit that only carries the span
    itself (a ``(start, end)`` tuple, an offset string, …) still counts; ``None``,
    ``""`` and empty containers read as *no span*.
    """
    flag = _get(hit, "has_span", None)
    if flag is not None:
        return bool(flag)
    return bool(_get(hit, "span", None))


def _confidence_of(hit: Any) -> float | None:
    """Numeric confidence, or ``None`` when absent (bools are not confidences)."""
    val = _get(hit, "confidence", None)
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    return None


def _evidence_count_of(hit: Any) -> int:
    val = _get(hit, "evidence_count", 0)
    if isinstance(val, bool):
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    return 0


def _node_dict(hit: Any) -> dict[str, Any]:
    """A plain-dict node view for the delegated primitive (empty if no node)."""
    node = _get(hit, "node", None)
    return dict(node) if isinstance(node, Mapping) else {}


def _limit(top_n: int | None, n: int) -> int:
    """Clamp ``top_n`` into ``[0, n]``; ``None`` means "keep all"."""
    if top_n is None:
        return n
    return max(0, min(int(top_n), n))


def _penalties(
    hit: Any,
    *,
    confidence_threshold: float,
    missing_span_penalty: float,
    low_confidence_penalty: float,
) -> tuple[float, float]:
    """(span_penalty, confidence_penalty) for one hit under §12.9 rules."""
    span_pen = 0.0 if _has_span(hit) else missing_span_penalty
    conf = _confidence_of(hit)
    conf_pen = low_confidence_penalty if conf is not None and conf < confidence_threshold else 0.0
    return span_pen, conf_pen


def _ordered_indices(
    items: list[Any],
    *,
    enabled: bool,
    limit: int,
    confidence_threshold: float,
    missing_span_penalty: float,
    low_confidence_penalty: float,
) -> tuple[list[int], dict[int, tuple[float, float, float, float]]]:
    """Compute the reranked order of original indices and per-index penalties.

    Returns ``(order, adj)`` where ``order`` is the truncated list of input
    indices in final rank order and ``adj[idx] = (base, adjusted, span_pen,
    conf_pen)``. When ``enabled`` is False this is a passthrough: input order,
    no penalties, ``adj`` empty (the caller treats missing entries as zero-penalty).
    """
    n = len(items)
    if not enabled:
        return list(range(n))[:limit], {}

    adj: dict[int, tuple[float, float, float, float]] = {}
    cands: list[dict[str, Any]] = []
    for idx, hit in enumerate(items):
        base = _score_of(hit)
        span_pen, conf_pen = _penalties(
            hit,
            confidence_threshold=confidence_threshold,
            missing_span_penalty=missing_span_penalty,
            low_confidence_penalty=low_confidence_penalty,
        )
        adjusted = base - span_pen - conf_pen
        adj[idx] = (base, adjusted, span_pen, conf_pen)
        cands.append({"id": str(idx), "score": adjusted, "node": _node_dict(hit)})

    # weight=0.0 → evidence_boost_rerank collapses to a stable sort by the adjusted
    # score, ties resolved toward earlier input order (deterministic).
    ranked = evidence_boost_rerank(cands, weight=0.0)
    order = [int(item.id) for item in ranked][:limit]
    return order, adj


def rerank(
    query: str,
    hits: Iterable[Any],
    *,
    top_n: int = DEFAULT_TOP_N,
    enabled: bool = True,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    missing_span_penalty: float = MISSING_SPAN_PENALTY,
    low_confidence_penalty: float = LOW_CONFIDENCE_PENALTY,
) -> list[Any]:
    """Rerank fusion ``hits`` by span / confidence penalties, truncated to ``top_n``.

    Returns the *original* hit objects (identity preserved) reordered so that, at
    equal fusion score, a hit **with** a source span outranks one without, and a
    hit whose ``confidence`` is below ``confidence_threshold`` is demoted below a
    higher-confidence peer. ``enabled=False`` is a deterministic passthrough: the
    input order is returned unchanged, only truncated to ``top_n``. ``query`` is
    accepted for interface parity with query-aware rerankers; penalties here are
    query-independent (relevance already lives in each hit's ``score``).
    """
    items = list(hits)
    limit = _limit(top_n, len(items))
    order, _ = _ordered_indices(
        items,
        enabled=enabled,
        limit=limit,
        confidence_threshold=confidence_threshold,
        missing_span_penalty=missing_span_penalty,
        low_confidence_penalty=low_confidence_penalty,
    )
    return [items[i] for i in order]


def rerank_scored(
    query: str,
    hits: Iterable[Any],
    *,
    top_n: int = DEFAULT_TOP_N,
    enabled: bool = True,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    missing_span_penalty: float = MISSING_SPAN_PENALTY,
    low_confidence_penalty: float = LOW_CONFIDENCE_PENALTY,
) -> list[HitScore]:
    """Like :func:`rerank` but return frozen :class:`HitScore` rows (§12.9).

    Each row exposes the base fusion score, the span / confidence penalties, the
    resulting adjusted score and the final ``rank`` — the auditable breakdown of
    *why* the order came out the way it did. Ordering, truncation and the
    passthrough semantics are identical to :func:`rerank`.
    """
    items = list(hits)
    limit = _limit(top_n, len(items))
    order, adj = _ordered_indices(
        items,
        enabled=enabled,
        limit=limit,
        confidence_threshold=confidence_threshold,
        missing_span_penalty=missing_span_penalty,
        low_confidence_penalty=low_confidence_penalty,
    )
    out: list[HitScore] = []
    for rank, idx in enumerate(order):
        hit = items[idx]
        base_default = _score_of(hit)
        base, adjusted, span_pen, conf_pen = adj.get(idx, (base_default, base_default, 0.0, 0.0))
        out.append(
            HitScore(
                id=_id_of(hit),
                base_score=round(base, 6),
                adjusted_score=round(adjusted, 6),
                span_penalty=round(span_pen, 6),
                confidence_penalty=round(conf_pen, 6),
                has_span=_has_span(hit),
                confidence=_confidence_of(hit),
                evidence_count=_evidence_count_of(hit),
                rank=rank,
            )
        )
    return out

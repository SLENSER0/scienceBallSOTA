"""Human-readable decomposition of a single hit's rerank adjustment (§12.15).

The §12.9 rerank pass (:mod:`kg_retrievers.rerank_api`) demotes evidentially-weak
hits by subtracting two penalties from the fusion ``score``:

* a **missing-source-span penalty** (штраф за отсутствие текстовой привязки) when
  the hit cannot point at the span of source text it was extracted from;
* a **low-confidence penalty** (штраф за низкую уверенность) when the hit's
  ``confidence`` falls *strictly* below the threshold.

§12.15 asks: for one hit, *why* did its score move the way it did?
:func:`explain_rerank` answers this without re-implementing any scoring — it
delegates the penalty arithmetic to :func:`kg_retrievers.rerank_api.rerank_scored`
and repackages the result as a frozen :class:`RerankExplanation`
(«объяснение переранжирования»):

``final_score = base_score - span_penalty - confidence_penalty``

plus a ``factors`` list that enumerates *only the penalties that were actually
applied* — an empty list means «штрафов нет» (a clean hit whose final score equals
its base score). Each entry is a frozen :class:`RerankFactor` carrying the penalty
name, its magnitude and a short RU/EN reason, so a UI or audit log can render the
breakdown verbatim.

This module is **pure python** and read-only over the hit: it never edits
``rerank_api`` and never mutates the hit. A *hit* is the same lenient shape
``rerank_api`` accepts — a ``Mapping`` **or** an object exposing ``score``,
``has_span`` / ``span`` and ``confidence``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_retrievers.rerank_api import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    LOW_CONFIDENCE_PENALTY,
    MISSING_SPAN_PENALTY,
    rerank_scored,
)

__all__ = [
    "RerankFactor",
    "RerankExplanation",
    "explain_rerank",
    "SPAN_FACTOR",
    "CONFIDENCE_FACTOR",
]

# Stable factor names — the keys a UI / audit log can switch on (RU/EN reasons
# live in the ``reason`` field so the names stay machine-friendly).
SPAN_FACTOR: str = "missing_span"
CONFIDENCE_FACTOR: str = "low_confidence"

_SPAN_REASON = "no source span attached — нет текстовой привязки к источнику"
_CONFIDENCE_REASON = "confidence below threshold — уверенность ниже порога"


@dataclass(frozen=True)
class RerankFactor:
    """One applied penalty in a rerank decomposition (§12.15).

    ``penalty`` is the non-negative magnitude **subtracted** from the base score
    (``delta`` is its signed form, ``-penalty``). ``reason`` is a short RU/EN gloss
    suitable for display. A :class:`RerankFactor` only ever exists for a penalty
    that *fired*; a zero penalty is omitted from :attr:`RerankExplanation.factors`.
    """

    name: str
    penalty: float
    reason: str

    @property
    def delta(self) -> float:
        """Signed contribution to the final score (always ``<= 0``)."""
        return -self.penalty

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "penalty": self.penalty,
            "delta": self.delta,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RerankExplanation:
    """Why one hit's rerank score moved: base minus penalties (§12.15).

    Invariants (all values rounded to 6 dp):

    * ``final_score == base_score - span_penalty - confidence_penalty``;
    * ``final_score == base_score - sum(f.penalty for f in factors)``;
    * ``final_score <= base_score`` (penalties never *raise* a score);
    * ``span_penalty >= 0`` and ``confidence_penalty >= 0``;
    * ``factors`` lists exactly the penalties that fired — empty when none did.
    """

    id: str | None
    base_score: float
    span_penalty: float
    confidence_penalty: float
    final_score: float
    factors: tuple[RerankFactor, ...]

    @property
    def total_penalty(self) -> float:
        """Sum of the applied penalties (``base_score - final_score``)."""
        return round(self.span_penalty + self.confidence_penalty, 6)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "base_score": self.base_score,
            "span_penalty": self.span_penalty,
            "confidence_penalty": self.confidence_penalty,
            "final_score": self.final_score,
            "total_penalty": self.total_penalty,
            "factors": [f.as_dict() for f in self.factors],
        }


def explain_rerank(
    hit: Any,
    *,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    missing_span_penalty: float = MISSING_SPAN_PENALTY,
    low_confidence_penalty: float = LOW_CONFIDENCE_PENALTY,
) -> RerankExplanation:
    """Decompose the §12.9 rerank adjustment of a single ``hit`` (§12.15).

    Delegates the penalty arithmetic to
    :func:`kg_retrievers.rerank_api.rerank_scored` (so the numbers match the real
    pass exactly), then repackages the breakdown as a frozen
    :class:`RerankExplanation`. The thresholds / penalty magnitudes are forwarded
    for parity with the rerank pass; the hit is never mutated.
    """
    scored = rerank_scored(
        "",
        [hit],
        confidence_threshold=confidence_threshold,
        missing_span_penalty=missing_span_penalty,
        low_confidence_penalty=low_confidence_penalty,
    )[0]

    span_penalty = scored.span_penalty
    confidence_penalty = scored.confidence_penalty
    # Recompute from the parts so the invariant final == base - penalties holds by
    # construction rather than trusting the delegated adjusted_score.
    final_score = round(scored.base_score - span_penalty - confidence_penalty, 6)

    factors: list[RerankFactor] = []
    if span_penalty > 0:
        factors.append(RerankFactor(name=SPAN_FACTOR, penalty=span_penalty, reason=_SPAN_REASON))
    if confidence_penalty > 0:
        factors.append(
            RerankFactor(
                name=CONFIDENCE_FACTOR, penalty=confidence_penalty, reason=_CONFIDENCE_REASON
            )
        )

    return RerankExplanation(
        id=scored.id,
        base_score=scored.base_score,
        span_penalty=span_penalty,
        confidence_penalty=confidence_penalty,
        final_score=final_score,
        factors=tuple(factors),
    )

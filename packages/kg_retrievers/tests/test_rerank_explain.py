"""Tests for the §12.15 rerank explanation (pure-python decomposition).

Every expected value is hand-computed from the §12.9 module constants:
``MISSING_SPAN_PENALTY = 0.5``, ``LOW_CONFIDENCE_PENALTY = 0.3`` and
``DEFAULT_CONFIDENCE_THRESHOLD = 0.5``. final = base - span_pen - conf_pen.
"""

from __future__ import annotations

from types import SimpleNamespace

from kg_retrievers.rerank_api import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    LOW_CONFIDENCE_PENALTY,
    MISSING_SPAN_PENALTY,
)
from kg_retrievers.rerank_explain import (
    CONFIDENCE_FACTOR,
    SPAN_FACTOR,
    RerankExplanation,
    RerankFactor,
    explain_rerank,
)


def test_span_penalty_shown_when_no_span() -> None:
    # High confidence (0.9 >= 0.5) so ONLY the missing-span penalty fires: the hit
    # carries no span at all -> span_penalty = 0.5, confidence_penalty = 0.
    hit = {"id": "h1", "score": 1.0, "has_span": False, "confidence": 0.9}
    exp = explain_rerank(hit)
    assert exp.span_penalty == MISSING_SPAN_PENALTY  # 0.5
    assert exp.confidence_penalty == 0.0
    # final = 1.0 - 0.5 - 0.0 = 0.5
    assert exp.final_score == 0.5
    # exactly one factor, the missing-span one, magnitude 0.5, delta -0.5.
    assert [f.name for f in exp.factors] == [SPAN_FACTOR]
    assert exp.factors[0].penalty == 0.5
    assert exp.factors[0].delta == -0.5


def test_confidence_penalty_for_low_confidence() -> None:
    # Has a span (no span penalty) but confidence 0.2 < 0.5 threshold -> ONLY the
    # low-confidence penalty fires: confidence_penalty = 0.3, span_penalty = 0.
    hit = {"id": "h2", "score": 0.8, "span": (3, 9), "confidence": 0.2}
    exp = explain_rerank(hit)
    assert exp.span_penalty == 0.0
    assert exp.confidence_penalty == LOW_CONFIDENCE_PENALTY  # 0.3
    # final = 0.8 - 0.0 - 0.3 = 0.5
    assert exp.final_score == 0.5
    assert [f.name for f in exp.factors] == [CONFIDENCE_FACTOR]
    assert exp.factors[0].penalty == 0.3


def test_final_equals_base_minus_both_penalties() -> None:
    # No span AND low confidence: both penalties fire and stack.
    hit = {"id": "h3", "score": 1.0, "has_span": False, "confidence": 0.1}
    exp = explain_rerank(hit)
    assert exp.span_penalty == 0.5
    assert exp.confidence_penalty == 0.3
    # final = 1.0 - 0.5 - 0.3 = 0.2
    assert exp.final_score == 0.2
    # The core invariant, two ways:
    assert exp.final_score == exp.base_score - exp.span_penalty - exp.confidence_penalty
    assert exp.final_score == round(exp.base_score - sum(f.penalty for f in exp.factors), 6)


def test_factors_list_enumerates_both_applied_penalties() -> None:
    hit = {"id": "h4", "score": 0.9, "has_span": False, "confidence": 0.0}
    exp = explain_rerank(hit)
    assert [f.name for f in exp.factors] == [SPAN_FACTOR, CONFIDENCE_FACTOR]
    assert [f.penalty for f in exp.factors] == [0.5, 0.3]
    # Ordered span-then-confidence; each carries an RU/EN reason string.
    assert all(isinstance(f, RerankFactor) for f in exp.factors)
    assert "источник" in exp.factors[0].reason and "span" in exp.factors[0].reason
    assert "порог" in exp.factors[1].reason and "confidence" in exp.factors[1].reason
    # total_penalty is the sum, and equals base - final.
    assert exp.total_penalty == 0.8
    assert exp.total_penalty == round(exp.base_score - exp.final_score, 6)


def test_no_penalty_hit_has_empty_factors_and_final_equals_base() -> None:
    # Has a span and confidence 0.9 (>= 0.5): nothing fires.
    hit = {"id": "clean", "score": 0.7, "span": "s1", "confidence": 0.9}
    exp = explain_rerank(hit)
    assert exp.span_penalty == 0.0
    assert exp.confidence_penalty == 0.0
    assert exp.factors == ()
    assert exp.final_score == exp.base_score == 0.7
    assert exp.total_penalty == 0.0


def test_confidence_at_threshold_is_not_penalised() -> None:
    # confidence == threshold (0.5) is NOT strictly below -> no confidence penalty.
    hit = {"id": "edge", "score": 0.6, "span": (0, 1), "confidence": DEFAULT_CONFIDENCE_THRESHOLD}
    exp = explain_rerank(hit)
    assert exp.confidence_penalty == 0.0
    assert exp.factors == ()
    assert exp.final_score == 0.6


def test_bounded_final_never_above_base_never_below_base_minus_max() -> None:
    max_total = MISSING_SPAN_PENALTY + LOW_CONFIDENCE_PENALTY  # 0.8
    for has_span, conf in [(True, 0.9), (False, 0.9), (True, 0.1), (False, 0.1)]:
        hit = {"id": "b", "score": 1.0, "has_span": has_span, "confidence": conf}
        exp = explain_rerank(hit)
        assert 0.0 <= exp.span_penalty <= MISSING_SPAN_PENALTY
        assert 0.0 <= exp.confidence_penalty <= LOW_CONFIDENCE_PENALTY
        # penalties only demote: base - max_total <= final <= base.
        assert exp.base_score - max_total <= exp.final_score <= exp.base_score
        # every applied factor is a genuine (positive) penalty.
        assert all(f.penalty > 0 for f in exp.factors)


def test_as_dict_is_serialisable_and_round_trips_values() -> None:
    hit = {"id": "d1", "score": 1.0, "has_span": False, "confidence": 0.2}
    exp = explain_rerank(hit)
    d = exp.as_dict()
    assert d["id"] == "d1"
    assert d["base_score"] == 1.0
    assert d["span_penalty"] == 0.5
    assert d["confidence_penalty"] == 0.3
    assert d["final_score"] == 0.2
    assert d["total_penalty"] == 0.8
    # factors serialises to a plain list of plain dicts (no dataclasses left).
    assert isinstance(d["factors"], list)
    assert d["factors"] == [
        {"name": SPAN_FACTOR, "penalty": 0.5, "delta": -0.5, "reason": exp.factors[0].reason},
        {
            "name": CONFIDENCE_FACTOR,
            "penalty": 0.3,
            "delta": -0.3,
            "reason": exp.factors[1].reason,
        },
    ]


def test_accepts_object_hits_and_reads_id() -> None:
    # rerank_api reads hits leniently; explain must too. An object with a span
    # attribute and low confidence -> only the confidence penalty fires.
    hit = SimpleNamespace(id=42, score=0.8, span=(1, 4), confidence=0.3)
    exp = explain_rerank(hit)
    assert isinstance(exp, RerankExplanation)
    assert exp.id == "42"  # coerced to str like rerank_api does
    assert exp.span_penalty == 0.0
    assert exp.confidence_penalty == 0.3
    assert exp.final_score == 0.5
    assert [f.name for f in exp.factors] == [CONFIDENCE_FACTOR]


def test_custom_penalty_magnitudes_are_forwarded() -> None:
    # Override the penalties -> the decomposition uses the overridden values.
    hit = {"id": "cfg", "score": 1.0, "has_span": False, "confidence": 0.1}
    exp = explain_rerank(hit, missing_span_penalty=0.25, low_confidence_penalty=0.1)
    assert exp.span_penalty == 0.25
    assert exp.confidence_penalty == 0.1
    # final = 1.0 - 0.25 - 0.1 = 0.65
    assert exp.final_score == 0.65
    assert [f.penalty for f in exp.factors] == [0.25, 0.1]

"""Tests for the §12.9 rerank entrypoint (span/confidence penalties + on-off).

Every expected value is hand-computed from the module constants:
``MISSING_SPAN_PENALTY = 0.5``, ``LOW_CONFIDENCE_PENALTY = 0.3`` and
``DEFAULT_CONFIDENCE_THRESHOLD = 0.5``. adjusted = score - span_pen - conf_pen.
"""

from __future__ import annotations

from types import SimpleNamespace

from kg_retrievers.rerank_api import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    LOW_CONFIDENCE_PENALTY,
    MISSING_SPAN_PENALTY,
    HitScore,
    rerank,
    rerank_scored,
)


def test_span_hit_outranks_otherwise_equal_no_span_hit() -> None:
    # Equal fusion score & confidence; only the span presence differs. The hit
    # WITHOUT a span is penalised by 0.5 and must fall below the span hit even
    # though it was first in the input fusion order.
    no_span = {"id": "no", "score": 1.0, "has_span": False, "confidence": 0.9, "evidence_count": 3}
    with_span = {"id": "yes", "score": 1.0, "span": (0, 5), "confidence": 0.9, "evidence_count": 3}
    out = rerank("q", [no_span, with_span])
    assert [h["id"] for h in out] == ["yes", "no"]
    assert out[0] is with_span  # original objects returned, identity preserved
    # Breakdown: yes -> 1.0 - 0 - 0 = 1.0 ; no -> 1.0 - 0.5 - 0 = 0.5.
    scored = rerank_scored("q", [no_span, with_span])
    assert [s.adjusted_score for s in scored] == [1.0, 0.5]
    assert scored[1].span_penalty == MISSING_SPAN_PENALTY


def test_low_confidence_hit_demoted_below_high_confidence_peer() -> None:
    # Equal fusion score, both have spans; only confidence differs. The 0.2 hit
    # is below the 0.5 threshold -> penalised 0.3 -> ranks below the 0.9 peer.
    low = {"id": "low", "score": 0.8, "span": "s1", "confidence": 0.2, "evidence_count": 2}
    high = {"id": "high", "score": 0.8, "span": "s1", "confidence": 0.9, "evidence_count": 2}
    out = rerank("q", [low, high])
    assert [h["id"] for h in out] == ["high", "low"]
    scored = rerank_scored("q", [low, high])
    # high -> 0.8 - 0 - 0 = 0.8 ; low -> 0.8 - 0 - 0.3 = 0.5.
    assert scored[0].adjusted_score == 0.8
    assert scored[0].confidence_penalty == 0.0
    assert scored[1].adjusted_score == 0.5
    assert scored[1].confidence_penalty == LOW_CONFIDENCE_PENALTY


def test_disabled_is_deterministic_passthrough_of_input_order() -> None:
    # enabled=False must return the EXACT input order (no penalties, no reorder),
    # even though enabling would reshuffle these three.
    a = {"id": "a", "score": 0.3, "has_span": False, "confidence": 0.1}
    b = {"id": "b", "score": 0.9, "span": (1, 2), "confidence": 0.9}
    c = {"id": "c", "score": 0.6, "has_span": False, "confidence": 0.9}
    hits = [a, b, c]
    out = rerank("q", hits, enabled=False)
    assert [h["id"] for h in out] == ["a", "b", "c"]
    assert out[0] is a and out[1] is b and out[2] is c
    # Contrast: with the pass enabled the order changes (b, c, a by adjusted score).
    assert [h["id"] for h in rerank("q", hits, enabled=True)] == ["b", "c", "a"]
    # Passthrough scored rows carry zero penalties and adjusted == base.
    scored = rerank_scored("q", hits, enabled=False)
    assert [s.adjusted_score for s in scored] == [0.3, 0.9, 0.6]
    assert all(s.span_penalty == 0.0 and s.confidence_penalty == 0.0 for s in scored)


def test_top_n_truncates_to_the_best_rows() -> None:
    hits = [
        {"id": "h0", "score": 0.1, "span": "x", "confidence": 0.9},
        {"id": "h1", "score": 0.5, "span": "x", "confidence": 0.9},
        {"id": "h2", "score": 0.9, "span": "x", "confidence": 0.9},
        {"id": "h3", "score": 0.7, "span": "x", "confidence": 0.9},
        {"id": "h4", "score": 0.3, "span": "x", "confidence": 0.9},
    ]
    out = rerank("q", hits, top_n=2)
    assert [h["id"] for h in out] == ["h2", "h3"]  # top two by score (all unpenalised)
    assert len(rerank("q", hits, top_n=2)) == 2
    # Passthrough also truncates, preserving input order.
    assert [h["id"] for h in rerank("q", hits, top_n=3, enabled=False)] == ["h0", "h1", "h2"]


def test_ties_are_stable_and_deterministic() -> None:
    # All rows identical in score/span/confidence -> equal adjusted scores -> the
    # input order must be preserved and repeatable across calls.
    hits = [
        {"id": "t0", "score": 0.5, "span": "s", "confidence": 0.9},
        {"id": "t1", "score": 0.5, "span": "s", "confidence": 0.9},
        {"id": "t2", "score": 0.5, "span": "s", "confidence": 0.9},
    ]
    first = [h["id"] for h in rerank("q", hits)]
    second = [h["id"] for h in rerank("q", hits)]
    assert first == ["t0", "t1", "t2"]
    assert first == second


def test_empty_hits_returns_empty() -> None:
    assert rerank("q", []) == []
    assert rerank_scored("q", []) == []
    assert rerank("q", [], enabled=False) == []


def test_single_hit_passes_through_at_rank_zero() -> None:
    hit = {"id": "solo", "score": 0.42, "has_span": False, "confidence": 0.1, "evidence_count": 7}
    out = rerank("q", [hit])
    assert len(out) == 1 and out[0] is hit
    scored = rerank_scored("q", [hit])
    assert len(scored) == 1
    row = scored[0]
    assert row.id == "solo"
    assert row.rank == 0
    assert row.base_score == 0.42
    # No span (-0.5) and confidence 0.1 < 0.5 (-0.3): 0.42 - 0.5 - 0.3 = -0.38.
    assert row.adjusted_score == -0.38
    assert row.span_penalty == 0.5
    assert row.confidence_penalty == 0.3
    assert row.evidence_count == 7


def test_object_hits_and_missing_confidence() -> None:
    # Hits may be arbitrary objects (attribute access), and a hit with no
    # confidence field is NOT confidence-penalised (unknown != low).
    span_obj = SimpleNamespace(id="obj_span", score=0.6, span=(3, 9), evidence_count=1)
    bare_obj = SimpleNamespace(id="obj_bare", score=0.6, has_span=False, evidence_count=1)
    out = rerank("q", [bare_obj, span_obj])
    assert [h.id for h in out] == ["obj_span", "obj_bare"]
    scored = rerank_scored("q", [bare_obj, span_obj])
    by_id = {s.id: s for s in scored}
    # span_obj: has span, no confidence -> no penalty at all -> 0.6.
    assert by_id["obj_span"].adjusted_score == 0.6
    assert by_id["obj_span"].confidence is None
    assert by_id["obj_span"].confidence_penalty == 0.0
    # bare_obj: no span (-0.5), still no confidence penalty -> 0.6 - 0.5 = 0.1.
    assert by_id["obj_bare"].adjusted_score == 0.1
    assert by_id["obj_bare"].confidence_penalty == 0.0


def test_confidence_exactly_at_threshold_is_not_penalised() -> None:
    # Penalty is for confidence STRICTLY below the threshold.
    at = {"id": "at", "score": 0.7, "span": "s", "confidence": DEFAULT_CONFIDENCE_THRESHOLD}
    below = {"id": "below", "score": 0.7, "span": "s", "confidence": 0.49}
    scored = rerank_scored("q", [at, below])
    by_id = {s.id: s for s in scored}
    assert by_id["at"].confidence_penalty == 0.0
    assert by_id["at"].adjusted_score == 0.7
    assert by_id["below"].confidence_penalty == LOW_CONFIDENCE_PENALTY
    assert [s.id for s in scored] == ["at", "below"]


def test_hitscore_as_dict_and_frozen() -> None:
    row = HitScore(
        id="x",
        base_score=0.5,
        adjusted_score=0.2,
        span_penalty=0.3,
        confidence_penalty=0.0,
        has_span=True,
        confidence=0.6,
        evidence_count=2,
        rank=1,
    )
    assert row.as_dict() == {
        "id": "x",
        "base_score": 0.5,
        "adjusted_score": 0.2,
        "span_penalty": 0.3,
        "confidence_penalty": 0.0,
        "has_span": True,
        "confidence": 0.6,
        "evidence_count": 2,
        "rank": 1,
    }
    try:
        row.rank = 5  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - only runs if the dataclass is not frozen
        raise AssertionError("HitScore must be frozen")

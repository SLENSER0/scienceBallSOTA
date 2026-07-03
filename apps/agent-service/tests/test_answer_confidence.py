"""§13.17 тесты агрегации уверенности ответа / answer-confidence aggregation tests.

Каждый расчёт проверяем вручную / every expectation is hand-checked against the
documented formula: ``score = clamp(mean(evidence) - gap_step*len(gaps)
- contradiction_step*len(contradictions), 0, 1)`` then capped by ``verifier_cap``.
"""

from __future__ import annotations

import orjson
import pytest
from agent_service.answer_confidence import (
    ConfidenceBreakdown,
    compute_answer_confidence,
)


def _ev(*values: float) -> list[dict]:
    """Helper: evidence dicts carrying the given ``confidence`` values."""
    return [{"confidence": v} for v in values]


def test_base_is_mean_no_penalties() -> None:
    """(1) two evidence at 0.8/0.6, no gaps/contradictions -> base 0.7, score 0.7."""
    out = compute_answer_confidence(_ev(0.8, 0.6), [], [])
    assert out.base == pytest.approx(0.7)
    assert out.score == pytest.approx(0.7)
    assert out.gap_penalty == 0.0
    assert out.contradiction_penalty == 0.0
    assert out.verifier_cap is None


def test_empty_evidence_zero_base_zero_score() -> None:
    """(2) empty evidence -> base 0.0 and score 0.0."""
    out = compute_answer_confidence([], [], [])
    assert out.base == 0.0
    assert out.score == 0.0


def test_one_gap_subtracts_exactly_gap_step() -> None:
    """(3) one gap subtracts exactly ``gap_step`` from the base."""
    out = compute_answer_confidence(_ev(0.8, 0.6), [{"id": "g1"}], [])
    assert out.gap_penalty == pytest.approx(0.05)
    assert out.score == pytest.approx(0.7 - 0.05)


def test_two_contradictions_subtract_two_steps() -> None:
    """(4) two contradictions subtract ``2 * contradiction_step``."""
    out = compute_answer_confidence(_ev(0.8, 0.6), [], [{"a": 1}, {"b": 2}])
    assert out.contradiction_penalty == pytest.approx(0.2)
    assert out.score == pytest.approx(0.7 - 0.2)


def test_penalties_clamped_at_zero() -> None:
    """(5) penalties never push the score below 0.0 (clamped)."""
    # base 0.5, five gaps (-0.25) plus six contradictions (-0.6) => raw -0.35 -> 0.0
    out = compute_answer_confidence(
        _ev(0.5),
        [{"id": i} for i in range(5)],
        [{"id": i} for i in range(6)],
    )
    assert out.score == 0.0
    assert out.base == pytest.approx(0.5)


def test_verifier_cap_below_score_caps() -> None:
    """(6) ``verifier_cap=0.5`` caps a 0.7 score to 0.5."""
    out = compute_answer_confidence(_ev(0.8, 0.6), [], [], verifier_cap=0.5)
    assert out.verifier_cap == 0.5
    assert out.score == pytest.approx(0.5)


def test_verifier_cap_above_score_no_change() -> None:
    """(7) ``verifier_cap=0.9`` above the computed 0.7 score leaves it unchanged."""
    out = compute_answer_confidence(_ev(0.8, 0.6), [], [], verifier_cap=0.9)
    assert out.verifier_cap == 0.9
    assert out.score == pytest.approx(0.7)


def test_as_dict_exposes_all_fields_orjson_safe() -> None:
    """(8) ``as_dict()`` exposes all five fields and is orjson-serialisable."""
    out = compute_answer_confidence(_ev(0.8, 0.6), [{"g": 1}], [], verifier_cap=0.5)
    assert isinstance(out, ConfidenceBreakdown)
    d = out.as_dict()
    assert set(d) == {
        "base",
        "gap_penalty",
        "contradiction_penalty",
        "verifier_cap",
        "score",
    }
    # round-trips through orjson unchanged
    assert orjson.loads(orjson.dumps(d)) == d

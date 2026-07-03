"""Gap priority scoring + ranking (§15.9).

All expected scores are hand-derivable from the weighted-average formula
``score = Σ w_i · s_i / Σ w_i`` with the default weights (absence 0.40,
importance 0.25, domain 0.20, novelty 0.15; they sum to 1.0) and neutral
default signal 0.5 (domain criticality default 0.5 too).
"""

from __future__ import annotations

import pytest

from kg_retrievers.gap_scoring import (
    DEFAULT_DOMAIN_CRITICALITY,
    ScoredGap,
    domain_criticality_score,
    gap_priority_score,
    next_experiment_hint,
    rank_gaps,
    score_gap,
)


def _gap(**over: object) -> dict:
    """A neutral base gap (all signals default to 0.5) with overrides."""
    base: dict = {"gap_type": "missing_property_value"}
    base.update(over)
    return base


def test_higher_absence_confidence_yields_higher_score() -> None:
    # Two gaps identical but for absence-confidence: the more-certain absence
    # must rank as the higher priority (§15.9).
    sure = gap_priority_score(_gap(absence_confidence=0.9))
    unsure = gap_priority_score(_gap(absence_confidence=0.3))
    assert sure > unsure
    # hand-check: only the absence term (w=0.40) moves; the other three stay 0.5.
    # sure   = 0.40*0.9 + (0.25+0.20+0.15)*0.5 = 0.36 + 0.30 = 0.66
    assert sure == pytest.approx(0.66)
    assert unsure == pytest.approx(0.42)  # 0.40*0.3 + 0.30 = 0.12 + 0.30


def test_rank_gaps_orders_by_score_descending() -> None:
    gaps = [
        _gap(gap_type="low", absence_confidence=0.1),
        _gap(gap_type="high", absence_confidence=0.95),
        _gap(gap_type="mid", absence_confidence=0.5),
    ]
    ranked = rank_gaps(gaps)
    assert [sg.gap_type for sg in ranked] == ["high", "mid", "low"]
    scores = [sg.score for sg in ranked]
    assert scores == sorted(scores, reverse=True)


def test_score_stays_in_unit_interval_for_extremes() -> None:
    # Even out-of-range signal values are clamped, so the score can't escape [0,1].
    hot = gap_priority_score(
        _gap(absence_confidence=5.0, importance=9.0, novelty=3.0, domain="водоподготовка")
    )
    cold = gap_priority_score(
        _gap(absence_confidence=-4.0, importance=-1.0, novelty=-2.0, domain="general")
    )
    assert 0.0 <= cold <= hot <= 1.0


def test_explanation_is_non_empty_russian() -> None:
    sg = score_gap(_gap(subject="полиамидная мембрана", absence_confidence=0.8))
    assert sg.explanation
    # contains Cyrillic and names the subject
    assert any("А" <= ch <= "я" or ch == "ё" for ch in sg.explanation)
    assert "полиамидная мембрана" in sg.explanation
    assert "приоритет" in sg.explanation.lower()


def test_missing_fields_fall_back_to_neutral_defaults() -> None:
    # An empty gap has no signals at all: every term defaults to 0.5, so the
    # weighted average is exactly 0.5 (§15.9).
    assert gap_priority_score({}) == pytest.approx(0.5)
    sg = score_gap({})
    assert sg.subject == "объект"  # RU fallback subject
    assert sg.domain is None
    assert sg.components == {
        "absence_confidence": 0.5,
        "importance": 0.5,
        "domain_criticality": 0.5,
        "novelty": 0.5,
    }
    assert sg.explanation and sg.hint  # still produced from defaults


def test_custom_weights_shift_ranking() -> None:
    # gap A: certain absence, unimportant subject. gap B: the opposite.
    a = _gap(gap_type="A", absence_confidence=0.9, importance=0.1)
    b = _gap(gap_type="B", absence_confidence=0.1, importance=0.9)
    # Default weights lean on absence → A wins.
    assert rank_gaps([a, b])[0].gap_type == "A"
    # Importance-heavy custom weights flip the ranking → B wins.
    importance_heavy = {
        "absence_confidence": 0.1,
        "importance": 0.9,
        "domain_criticality": 0.0,
        "novelty": 0.0,
    }
    flipped = rank_gaps([a, b], weights=importance_heavy)
    assert flipped[0].gap_type == "B"


def test_next_experiment_hint_mentions_the_subject() -> None:
    hint = next_experiment_hint(
        _gap(subject="графеновый оксид", property="проницаемость", domain="мембраны")
    )
    assert "графеновый оксид" in hint
    assert "проницаемость" in hint
    assert "мембраны" in hint
    assert hint.startswith("Провести эксперимент:")
    # a bare gap still yields a usable one-liner mentioning the fallback subject
    bare = next_experiment_hint({})
    assert "объект" in bare


def test_domain_criticality_raises_priority() -> None:
    # Same gap, more-critical domain → higher score. Water treatment (1.0) beats
    # the neutral default (0.5) via the domain term (w=0.20) → +0.10 (§24/§15.9).
    critical = gap_priority_score(_gap(domain="водоподготовка"))
    plain = gap_priority_score(_gap(domain="нечто неизвестное"))
    assert domain_criticality_score("водоподготовка") == pytest.approx(1.0)
    assert domain_criticality_score("нечто неизвестное") == pytest.approx(
        DEFAULT_DOMAIN_CRITICALITY
    )
    assert critical == pytest.approx(plain + 0.10)  # 0.20*(1.0-0.5)


def test_scored_gap_as_dict_round_trips() -> None:
    sg = score_gap(_gap(subject="цеолит", absence_confidence=0.7, domain="materials"))
    assert isinstance(sg, ScoredGap)
    dumped = sg.as_dict()
    assert set(dumped) == {
        "gap_type",
        "subject",
        "domain",
        "score",
        "explanation",
        "hint",
        "components",
    }
    assert dumped["subject"] == "цеолит"
    assert dumped["domain"] == "materials"
    same_gap = _gap(subject="цеолит", absence_confidence=0.7, domain="materials")
    assert dumped["score"] == gap_priority_score(same_gap)  # score matches the function
    # frozen dataclass: attributes cannot be reassigned
    with pytest.raises(AttributeError):
        sg.score = 0.0  # type: ignore[misc]

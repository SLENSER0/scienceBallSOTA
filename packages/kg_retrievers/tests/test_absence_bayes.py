"""§25.11 tests — standalone Bayesian absence scorer (hand-checked values)."""

from __future__ import annotations

from kg_retrievers.absence_bayes import (
    ABSTAIN,
    GENUINE_GAP,
    GENUINE_GAP_AT,
    POSSIBLE_MISS,
    POSSIBLE_MISS_AT,
    AbsenceProbabilities,
    posterior_absence,
    score_absence,
    verdict_from_probs,
)


def test_constants() -> None:
    assert POSSIBLE_MISS_AT == 0.60
    assert GENUINE_GAP_AT == 0.25


def test_perfect_recall_no_miss_genuine_gap() -> None:
    # (1) recall == 1.0 -> nothing was missed -> genuine gap.
    _p_ta, p_em = posterior_absence(0.5, 1.0)
    assert p_em == 0.0
    assert score_absence(0.5, 1.0).verdict == GENUINE_GAP


def test_zero_exists_prior_no_miss_genuine_gap() -> None:
    # (2) exists_prior == 0.0 -> the datum cannot exist -> no miss -> genuine gap.
    p_ta, p_em = posterior_absence(0.0, 0.2)
    assert p_em == 0.0
    assert p_ta == 1.0
    assert score_absence(0.0, 0.2).verdict == GENUINE_GAP


def test_high_exists_low_recall_possible_miss() -> None:
    # (3) 0.9 * 0.8 / (0.9 * 0.8 + 0.1) = 0.72 / 0.82 ~= 0.8780 > 0.6 -> possible_miss.
    _p_ta, p_em = posterior_absence(0.9, 0.2)
    assert abs(p_em - (0.72 / 0.82)) < 1e-9
    assert p_em > 0.6
    assert score_absence(0.9, 0.2).verdict == POSSIBLE_MISS


def test_posteriors_sum_to_one() -> None:
    # (4) p_truly_absent + p_extractor_missed == 1.0 (abs tol 1e-9).
    for prior, recall in [(0.9, 0.2), (0.3, 0.7), (0.55, 0.5), (0.0, 0.9), (1.0, 0.0)]:
        p_ta, p_em = posterior_absence(prior, recall)
        assert abs(p_ta + p_em - 1.0) < 1e-9


def test_verdict_abstain_middle() -> None:
    # (5) 0.4 sits strictly between 0.25 and 0.60 -> abstain.
    assert verdict_from_probs(0.4) == ABSTAIN


def test_verdict_genuine_gap_boundary_inclusive() -> None:
    # (6) exactly 0.25 -> genuine_gap (boundary inclusive).
    assert verdict_from_probs(0.25) == GENUINE_GAP


def test_verdict_possible_miss_boundary_inclusive() -> None:
    # (7) exactly 0.60 -> possible_miss (boundary inclusive).
    assert verdict_from_probs(0.60) == POSSIBLE_MISS


def test_out_of_range_recall_clamped() -> None:
    # (8) recall = 1.5 clamps to 1.0 -> 1 - r = 0 -> no miss.
    p_ta, p_em = posterior_absence(0.9, 1.5)
    assert p_em == 0.0
    assert p_ta == 1.0


def test_out_of_range_prior_clamped() -> None:
    # Symmetric clamp on the prior side: -0.5 -> 0.0 -> cannot be a miss.
    p_ta, p_em = posterior_absence(-0.5, 0.3)
    assert p_em == 0.0
    assert p_ta == 1.0


def test_degenerate_certain_exists_certain_recall() -> None:
    # π = 1 and r = 1: denominator collapses; a no-evidence cell is not a miss.
    p_ta, p_em = posterior_absence(1.0, 1.0)
    assert p_em == 0.0
    assert p_ta == 1.0


def test_score_absence_returns_dataclass_with_as_dict() -> None:
    probs = score_absence(0.9, 0.2)
    assert isinstance(probs, AbsenceProbabilities)
    d = probs.as_dict()
    assert set(d) == {"p_truly_absent", "p_extractor_missed", "verdict"}
    assert d["verdict"] == POSSIBLE_MISS
    assert abs(d["p_truly_absent"] + d["p_extractor_missed"] - 1.0) < 1e-9


def test_frozen_dataclass() -> None:
    probs = score_absence(0.5, 0.5)
    try:
        probs.verdict = "x"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject mutation
        raise AssertionError("AbsenceProbabilities must be frozen")

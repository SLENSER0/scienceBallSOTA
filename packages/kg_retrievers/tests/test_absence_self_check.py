"""Tests for §25.13 agent-facing absence self-check summary."""

from __future__ import annotations

from kg_retrievers.absence_self_check import (
    AbsenceSelfCheck,
    should_flag_hypothesis,
    summarize_absence,
)


def _gap(verdict: str, *, p_missed: float | None = None, calibrated: bool = True) -> dict:
    """Build one annotated-gap dict with a verdict, miss probability and meta."""
    return {
        "absence_verdict": verdict,
        "p_extractor_missed": p_missed,
        "absence_meta": {"calibrated": calibrated},
    }


def test_mixed_four_verdicts_counts_match() -> None:
    """(1) A mixed list of 4 verdicts yields matching per-verdict counts."""
    gaps = [
        _gap("genuine_gap"),
        _gap("possible_miss"),
        _gap("retracted"),
        _gap("abstain"),
    ]
    check = summarize_absence(gaps)
    assert check.n_gaps == 4
    assert check.n_genuine_gap == 1
    assert check.n_possible_miss == 1
    assert check.n_retracted == 1
    assert check.n_abstain == 1


def test_high_miss_risk_threshold() -> None:
    """(2) p_extractor_missed 0.7 counts as high-miss risk; 0.5 does not."""
    gaps = [
        _gap("genuine_gap", p_missed=0.7),
        _gap("genuine_gap", p_missed=0.5),
    ]
    check = summarize_absence(gaps, high_miss_at=0.6)
    assert check.n_high_miss_risk == 1


def test_calibrated_only_when_every_meta_calibrated() -> None:
    """(3) calibrated is True only when every gap's meta.calibrated is True."""
    all_cal = [_gap("genuine_gap", calibrated=True), _gap("abstain", calibrated=True)]
    assert summarize_absence(all_cal).calibrated is True

    one_bad = [_gap("genuine_gap", calibrated=True), _gap("abstain", calibrated=False)]
    assert summarize_absence(one_bad).calibrated is False


def test_warnings_non_empty_when_possible_miss_present() -> None:
    """(4) warnings is non-empty when a possible_miss exists."""
    check = summarize_absence([_gap("possible_miss")])
    assert check.warnings
    assert any("possible" in w.lower() for w in check.warnings)


def test_should_flag_genuine_gap_is_true() -> None:
    """(5) should_flag_hypothesis on a genuine_gap is True."""
    assert should_flag_hypothesis({"absence_verdict": "genuine_gap"}) is True


def test_should_flag_abstain_is_false() -> None:
    """(6) should_flag_hypothesis on an abstain is False."""
    assert should_flag_hypothesis({"absence_verdict": "abstain"}) is False


def test_should_flag_possible_miss_is_false() -> None:
    """possible_miss must also be held back (not presented as unstudied)."""
    assert should_flag_hypothesis({"absence_verdict": "possible_miss"}) is False


def test_empty_list_is_uncalibrated_with_no_warnings() -> None:
    """(7) An empty list yields n_gaps==0, calibrated False and warnings==[]."""
    check = summarize_absence([])
    assert check.n_gaps == 0
    assert check.calibrated is False
    assert check.warnings == []


def test_as_dict_possible_miss_count() -> None:
    """(8) as_dict()['n_possible_miss'] equals the possible_miss count."""
    gaps = [_gap("possible_miss"), _gap("possible_miss"), _gap("genuine_gap")]
    d = summarize_absence(gaps).as_dict()
    assert d["n_possible_miss"] == 2


def test_high_miss_warning_appended() -> None:
    """A high-miss-risk warning is appended when n_high_miss_risk > 0."""
    check = summarize_absence([_gap("genuine_gap", p_missed=0.9)])
    assert check.n_high_miss_risk == 1
    assert any("high" in w.lower() or "риск" in w.lower() for w in check.warnings)


def test_missing_p_missed_treated_as_zero() -> None:
    """A None/missing p_extractor_missed contributes no high-miss risk."""
    check = summarize_absence([{"absence_verdict": "genuine_gap"}])
    assert check.n_high_miss_risk == 0
    assert check.calibrated is False  # no absence_meta -> not calibrated


def test_dataclass_is_frozen() -> None:
    """AbsenceSelfCheck is frozen (immutable)."""
    check = summarize_absence([_gap("genuine_gap")])
    assert isinstance(check, AbsenceSelfCheck)
    try:
        check.n_gaps = 99  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected frozen dataclass")

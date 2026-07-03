"""Tests for the prevalence-weighted HalluMat PHCS (§23.35).

Hand-checkable arithmetic on tiny record sets ("проверяемая вручную").
"""

from __future__ import annotations

import pytest

from kg_eval.hallumat_phcs_score import PHCSReport, score_phcs


def _rec(hallucinated: bool, contradicted: bool, prevalence: float = 1.0) -> dict[str, object]:
    return {
        "hallucinated": hallucinated,
        "contradicted": contradicted,
        "prevalence": prevalence,
    }


def test_all_clean_scores_one_and_passes() -> None:
    records = [_rec(False, False) for _ in range(5)]
    report = score_phcs(records)
    assert report.phcs == 1.0
    assert report.hallucination_prevalence == 0.0
    assert report.contradiction_prevalence == 0.0
    assert report.passed is True


def test_all_failing_alpha_half_scores_zero() -> None:
    records = [_rec(True, True) for _ in range(4)]
    report = score_phcs(records, alpha=0.5)
    assert report.hallucination_prevalence == 1.0
    assert report.contradiction_prevalence == 1.0
    assert report.phcs == 0.0
    assert report.passed is False


def test_half_hallucinated_alpha_one_scores_half() -> None:
    # 4 unit-prevalence records, 2 hallucinated, none contradicted, alpha=1.0.
    records = [_rec(True, False), _rec(True, False), _rec(False, False), _rec(False, False)]
    report = score_phcs(records, alpha=1.0)
    assert report.hallucination_prevalence == 0.5
    assert report.contradiction_prevalence == 0.0
    assert report.phcs == 0.5


def test_prevalence_weights_hallucination_rate() -> None:
    # prevalence 3.0 hallucinated vs prevalence 1.0 clean -> 3/(3+1) = 0.75.
    records = [_rec(True, False, prevalence=3.0), _rec(False, False, prevalence=1.0)]
    report = score_phcs(records)
    assert report.hallucination_prevalence == 0.75
    assert report.total_prevalence == 4.0


def test_alpha_zero_ignores_hallucination_flags() -> None:
    # Vary hallucination flags but keep contradiction fixed; phcs must not move.
    a = score_phcs([_rec(True, False), _rec(True, True)], alpha=0.0)
    b = score_phcs([_rec(False, False), _rec(False, True)], alpha=0.0)
    assert a.phcs == b.phcs
    # Only contradiction (0.5 rate) drives it: phcs = 1 - 0.5 = 0.5.
    assert a.phcs == 0.5


def test_negative_prevalence_raises() -> None:
    with pytest.raises(ValueError):
        score_phcs([_rec(False, False, prevalence=-1.0)])


def test_empty_raises() -> None:
    with pytest.raises(ValueError):
        score_phcs([])


def test_gate_not_met_fails() -> None:
    # 10 records, 3 hallucinated, none contradicted, alpha=0.5 -> phcs 0.85.
    records = [_rec(True, False) for _ in range(3)] + [_rec(False, False) for _ in range(7)]
    report = score_phcs(records, alpha=0.5, gate=0.9)
    assert report.phcs == 0.85
    assert report.passed is False


def test_gate_met_passes_at_boundary() -> None:
    records = [_rec(True, False) for _ in range(3)] + [_rec(False, False) for _ in range(7)]
    report = score_phcs(records, alpha=0.5, gate=0.85)
    assert report.phcs == 0.85
    assert report.passed is True


def test_as_dict_includes_total_prevalence_and_rounds() -> None:
    records = [_rec(True, False, prevalence=2.0), _rec(False, True, prevalence=1.0)]
    report = score_phcs(records)
    d = report.as_dict()
    assert d["total_prevalence"] == 3.0
    assert d["n"] == 2
    assert d["passed"] is False
    assert set(d) == {
        "n",
        "total_prevalence",
        "hallucination_prevalence",
        "contradiction_prevalence",
        "phcs",
        "passed",
    }
    # hallucination = 2/3, contradiction = 1/3 -> rounded to 6 places.
    assert d["hallucination_prevalence"] == round(2 / 3, 6)
    assert d["contradiction_prevalence"] == round(1 / 3, 6)


def test_missing_prevalence_defaults_to_one() -> None:
    records = [
        {"hallucinated": True, "contradicted": False},
        {"hallucinated": False, "contradicted": False},
    ]
    report = score_phcs(records)
    assert report.total_prevalence == 2.0
    assert report.hallucination_prevalence == 0.5


def test_report_is_frozen() -> None:
    report = score_phcs([_rec(False, False)])
    assert isinstance(report, PHCSReport)
    with pytest.raises(AttributeError):
        report.phcs = 0.0  # type: ignore[misc]

"""Tests for the calibration drift regression gate (§23.25)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_eval.calibration_drift_gate import DriftReport, check_drift

# Perfectly calibrated run: bin@0.0 (conf 0, acc 0) + bin@1.0 (conf 1, acc 1).
# ECE == 0.0, Brier == 0.0 — both float-exact.
PERFECT: list[tuple[float, bool]] = [(0.0, False), (1.0, True)]


def test_identical_pairs_no_drift() -> None:
    """Same run twice -> zero deltas, not regressed, empty reasons."""
    report = check_drift(PERFECT, PERFECT)
    assert report.ece_delta == 0.0
    assert report.brier_delta == 0.0
    assert report.regressed is False
    assert report.reasons == ()


def test_candidate_worse_ece_regresses() -> None:
    """Candidate ECE worse by 0.05 (tol 0.02) -> regressed, 'ece' flagged."""
    # 20 pairs at conf 0.5, 11 True -> accuracy 0.55, gap 0.05, ECE == 0.05.
    candidate = [(0.5, True)] * 11 + [(0.5, False)] * 9
    report = check_drift(PERFECT, candidate, tol=0.02)
    assert report.ece_candidate == pytest.approx(0.05)
    assert report.ece_delta == pytest.approx(0.05)
    assert report.regressed is True
    assert "ece" in report.reasons


def test_exactly_tol_delta_not_regressed() -> None:
    """Delta exactly == tol passes (strict > gate)."""
    # conf 0.25 all False -> bin gap |0 - 0.25| = 0.25, ECE == 0.25 (float-exact).
    candidate = [(0.25, False), (0.25, False)]
    report = check_drift(PERFECT, candidate, tol=0.25)
    assert report.ece_delta == 0.25
    assert report.regressed is False
    assert report.reasons == ()


def test_brier_worsening_flags_brier_even_when_ece_ok() -> None:
    """Same ECE (delta 0) but worse Brier -> 'brier' reason, no 'ece'."""
    # conf 0.5, one True one False -> bin acc 0.5 == conf 0.5, ECE == 0.0;
    # Brier == (0.25 + 0.25) / 2 == 0.25.
    candidate = [(0.5, True), (0.5, False)]
    report = check_drift(PERFECT, candidate, tol=0.02)
    assert report.ece_delta == 0.0
    assert report.brier_delta == pytest.approx(0.25)
    assert report.regressed is True
    assert report.reasons == ("brier",)


def test_empty_candidate_raises() -> None:
    """Empty candidate is a caller bug."""
    with pytest.raises(ValueError):
        check_drift(PERFECT, [])


def test_empty_baseline_raises() -> None:
    """Empty baseline is a caller bug."""
    with pytest.raises(ValueError):
        check_drift([], PERFECT)


def test_as_dict_shapes_and_rounding() -> None:
    """as_dict()['regressed'] is bool and ece_delta is rounded to 4 dp."""
    candidate = [(0.5, True)] * 11 + [(0.5, False)] * 9
    report = check_drift(PERFECT, candidate, tol=0.02)
    d = report.as_dict()
    assert isinstance(d["regressed"], bool)
    assert d["ece_delta"] == 0.05  # round(0.05000000000000004, 4)
    assert "ece" in d["reasons"]


def test_frozen_dataclass() -> None:
    """DriftReport is immutable."""
    report = check_drift(PERFECT, PERFECT)
    assert isinstance(report, DriftReport)
    with pytest.raises(FrozenInstanceError):
        report.regressed = True  # type: ignore[misc]

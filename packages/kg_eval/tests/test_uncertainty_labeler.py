"""Tests for the uncertainty labeller (§23.25)."""

from __future__ import annotations

from kg_eval.uncertainty_labeler import (
    DEFAULT,
    LabelThresholds,
    label,
    label_batch,
)


def test_high_confidence() -> None:
    assert label(0.9) == "high confidence"


def test_conflict_beats_high_confidence() -> None:
    # Precedence: a conflict flag overrides even a high confidence score.
    assert label(0.9, has_conflict=True) == "conflicting"


def test_mid_confidence_needs_review() -> None:
    assert label(0.7) == "needs review"


def test_low_confidence_unsupported() -> None:
    assert label(0.1) == "unsupported"


def test_no_evidence_is_unsupported_even_at_high_conf() -> None:
    assert label(0.99, has_evidence=False) == "unsupported"


def test_estimated_flag() -> None:
    assert label(0.9, is_estimated=True) == "estimated"


def test_exact_high_boundary_is_high_confidence() -> None:
    # Inclusive lower bound: conf == high threshold -> high confidence.
    assert label(0.85) == "high confidence"


def test_low_band_still_needs_review() -> None:
    # conf in [low, review) maps to needs review, not unsupported.
    assert label(0.3) == "needs review"
    assert label(0.29) == "unsupported"


def test_conflict_precedes_no_evidence() -> None:
    assert label(0.5, has_conflict=True, has_evidence=False) == "conflicting"


def test_no_evidence_precedes_estimated() -> None:
    assert label(0.9, has_evidence=False, is_estimated=True) == "unsupported"


def test_as_dict_has_three_float_keys() -> None:
    d = DEFAULT.as_dict()
    assert set(d) == {"high", "review", "low"}
    assert all(isinstance(v, float) for v in d.values())
    assert d == {"high": 0.85, "review": 0.6, "low": 0.3}


def test_thresholds_are_frozen() -> None:
    import dataclasses

    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT.high = 0.5  # type: ignore[misc]


def test_custom_thresholds() -> None:
    strict = LabelThresholds(high=0.95, review=0.7, low=0.4)
    assert label(0.9, thresholds=strict) == "needs review"
    assert label(0.96, thresholds=strict) == "high confidence"


def test_label_batch() -> None:
    records = [
        {"confidence": 0.9},
        {"confidence": 0.9, "has_conflict": True},
        {"confidence": 0.7},
        {"confidence": 0.1},
        {"confidence": 0.99, "has_evidence": False},
        {"confidence": 0.9, "is_estimated": True},
        {},  # missing confidence -> defaults to 0.0 -> unsupported
    ]
    assert label_batch(records) == (
        "high confidence",
        "conflicting",
        "needs review",
        "unsupported",
        "unsupported",
        "estimated",
        "unsupported",
    )

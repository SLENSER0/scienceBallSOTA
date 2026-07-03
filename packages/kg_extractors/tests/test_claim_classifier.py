"""Rule-based claim_type / polarity classifier tests (§6.9)."""

from __future__ import annotations

import pytest

from kg_extractors.claim_classifier import (
    CLAIM_TYPES,
    POLARITIES,
    ClaimClass,
    classify_claim,
)

# ---------------------------------------------------------------------------
# Spec assertions (§6.9)
# ---------------------------------------------------------------------------


def test_recommendation_recommended() -> None:
    result = classify_claim("Aging at 180 °C is recommended for peak hardness")
    assert result.claim_type == "recommendation"
    assert result.polarity == "recommended"


def test_should_not_is_not_recommended() -> None:
    result = classify_claim("temperature should not exceed 200 °C")
    assert result.polarity == "not_recommended"
    assert result.claim_type == "recommendation"


def test_higher_than_is_comparison() -> None:
    assert classify_claim("showed higher strength than the baseline").claim_type == "comparison"


def test_limited_to_is_limitation() -> None:
    assert classify_claim("This study is limited to Al-Cu alloys").claim_type == "limitation"


def test_plain_measurement_is_finding() -> None:
    result = classify_claim("Hardness increased to 148 HV")
    assert result.claim_type == "finding"
    assert result.polarity == "neutral"


def test_cues_capture_recommend() -> None:
    assert "recommend" in classify_claim("we recommend aging").cues


def test_as_dict_shape() -> None:
    assert set(classify_claim("x").as_dict()) == {"claim_type", "polarity", "cues"}


# ---------------------------------------------------------------------------
# Rule-priority / negation contract (§6.9)
# ---------------------------------------------------------------------------


def test_avoid_is_not_recommended() -> None:
    result = classify_claim("avoid overheating above the solvus")
    assert result.claim_type == "recommendation"
    assert result.polarity == "not_recommended"


def test_should_not_beats_should() -> None:
    # «should not» must be checked before the plain «should» cue.
    result = classify_claim("the alloy should not be quenched in water")
    assert result.polarity == "not_recommended"
    assert "should not" in result.cues


def test_however_is_limitation() -> None:
    assert classify_claim("however, the fatigue data were incomplete").claim_type == "limitation"


def test_could_not_is_limitation() -> None:
    assert classify_claim("we could not resolve the second phase").claim_type == "limitation"


def test_compared_to_is_comparison() -> None:
    result = classify_claim("yield rose 12% compared to the as-cast state")
    assert result.claim_type == "comparison"
    assert "compared to" in result.cues


def test_outperforms_is_comparison() -> None:
    assert classify_claim("the T6 temper outperforms the T4").claim_type == "comparison"


def test_finding_has_empty_cues() -> None:
    assert classify_claim("Hardness increased to 148 HV").cues == ()


# ---------------------------------------------------------------------------
# Vocabulary + serialization + immutability contract (§6.9)
# ---------------------------------------------------------------------------


def test_result_type_and_polarity_in_vocab() -> None:
    result = classify_claim("we recommend aging")
    assert result.claim_type in CLAIM_TYPES
    assert result.polarity in POLARITIES


def test_as_dict_roundtrips_values() -> None:
    result = classify_claim("temperature should not exceed 200 °C")
    payload = result.as_dict()
    assert payload["claim_type"] == "recommendation"
    assert payload["polarity"] == "not_recommended"
    assert isinstance(payload["cues"], tuple)


def test_claim_class_is_frozen() -> None:
    cc = ClaimClass(claim_type="finding", polarity="neutral", cues=())
    with pytest.raises(AttributeError):
        cc.claim_type = "comparison"  # type: ignore[misc]


def test_rejects_unknown_claim_type() -> None:
    with pytest.raises(ValueError):
        ClaimClass(claim_type="bogus", polarity="neutral", cues=())


def test_rejects_unknown_polarity() -> None:
    with pytest.raises(ValueError):
        ClaimClass(claim_type="finding", polarity="bogus", cues=())

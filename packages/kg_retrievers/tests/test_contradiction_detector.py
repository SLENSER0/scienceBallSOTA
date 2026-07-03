"""Richer contradiction heuristics — hand-checked cases (§15.4).

Every expected value below is worked out by hand from the rules in
``kg_retrievers.contradiction_detector``:
- numeric relative divergence ``|a-b| / max(|a|,|b|)`` vs the 0.30 threshold;
- disjoint confidence intervals ``gap / (gap + span_a + span_b)``;
- opposite qualitative effect direction (``increase`` vs ``decrease``);
- ``likely_correct`` by ``evidence_strength`` rank (§3.6) then ``confidence``.
"""

from __future__ import annotations

from kg_retrievers.contradiction_detector import (
    ContradictionVerdict,
    classify_pair,
    detect_contradiction,
)


def test_numeric_divergence_same_unit() -> None:
    # |0.2-0.5| / max(0.2,0.5) = 0.3 / 0.5 = 0.60 >= 0.30 → contradiction.
    a = {"value_normalized": 0.2, "normalized_unit": "m/s"}
    b = {"value_normalized": 0.5, "normalized_unit": "m/s"}
    v = detect_contradiction(a, b)
    assert v.is_contradiction is True
    assert v.subtype == "numeric_divergence"
    assert abs(v.severity - 0.60) < 1e-9
    assert isinstance(v, ContradictionVerdict)


def test_same_value_different_unit_is_none() -> None:
    # Same number but incomparable units → no numeric divergence, no verdict.
    a = {"value_normalized": 5.0, "normalized_unit": "mpa"}
    b = {"value_normalized": 5.0, "normalized_unit": "psi"}
    v = detect_contradiction(a, b)
    assert v.is_contradiction is False
    assert v.subtype == "none"
    assert v.severity == 0.0
    assert v.reasons == ()


def test_disjoint_confidence_intervals() -> None:
    # Means equal (3.5) so numeric divergence cannot fire, yet CIs [1,2] & [5,6]
    # are disjoint: gap = 5-2 = 3, span = 1+1 = 2 → severity = 3/5 = 0.60.
    a = {"value_normalized": 3.5, "normalized_unit": "mpa", "ci_low": 1.0, "ci_high": 2.0}
    b = {"value_normalized": 3.5, "normalized_unit": "mpa", "ci_low": 5.0, "ci_high": 6.0}
    v = detect_contradiction(a, b)
    assert v.is_contradiction is True
    assert v.subtype == "ci_disjoint"
    assert abs(v.severity - 0.60) < 1e-9


def test_ci_disjoint_outranks_numeric_divergence() -> None:
    # Both rules fire (means 1.5 vs 5.5 diverge AND CIs are disjoint); the
    # disjoint-CI subtype has priority, and both reasons are reported.
    a = {"value_normalized": 1.5, "normalized_unit": "mpa", "ci_low": 1.0, "ci_high": 2.0}
    b = {"value_normalized": 5.5, "normalized_unit": "mpa", "ci_low": 5.0, "ci_high": 6.0}
    v = detect_contradiction(a, b)
    assert v.subtype == "ci_disjoint"
    assert len(v.reasons) == 2
    assert any("disjoint" in r for r in v.reasons)
    assert any("divergence" in r for r in v.reasons)


def test_opposite_effect_direction() -> None:
    # increase vs decrease → qualitative flip, the strongest subtype (severity 1).
    a = {"value_normalized": 10.0, "normalized_unit": "pct", "effect_direction": "increase"}
    b = {"value_normalized": 12.0, "normalized_unit": "pct", "effect_direction": "decrease"}
    v = detect_contradiction(a, b)
    assert v.is_contradiction is True
    assert v.subtype == "effect_direction"
    assert v.severity == 1.0


def test_likely_correct_prefers_peer_reviewed() -> None:
    # Contradiction present; peer_reviewed (rank 6) beats unverified (rank 1).
    a = {"value_normalized": 0.2, "normalized_unit": "m/s", "evidence_strength": "peer_reviewed"}
    b = {"value_normalized": 0.5, "normalized_unit": "m/s", "evidence_strength": "unverified"}
    assert detect_contradiction(a, b).likely_correct == "a"
    # Symmetric: swapping the sides swaps the winner to 'b'.
    assert detect_contradiction(b, a).likely_correct == "b"


def test_likely_correct_confidence_tiebreak() -> None:
    # Equal evidence strength → higher confidence wins the tiebreak.
    a = {
        "value_normalized": 0.2,
        "normalized_unit": "m/s",
        "evidence_strength": "internal_report",
        "confidence": 0.9,
    }
    b = {
        "value_normalized": 0.5,
        "normalized_unit": "m/s",
        "evidence_strength": "internal_report",
        "confidence": 0.4,
    }
    assert detect_contradiction(a, b).likely_correct == "a"


def test_severity_scales_with_divergence() -> None:
    # Larger relative divergence → larger severity.
    small = detect_contradiction(
        {"value_normalized": 0.2, "normalized_unit": "m/s"},
        {"value_normalized": 0.5, "normalized_unit": "m/s"},
    )  # rel 0.60
    large = detect_contradiction(
        {"value_normalized": 0.2, "normalized_unit": "m/s"},
        {"value_normalized": 0.9, "normalized_unit": "m/s"},
    )  # rel = 0.7 / 0.9 ≈ 0.778
    assert small.is_contradiction and large.is_contradiction
    assert large.severity > small.severity
    assert 0.0 <= small.severity <= 1.0 and 0.0 <= large.severity <= 1.0


def test_agreeing_values_is_none() -> None:
    # |0.50-0.52| / 0.52 ≈ 0.038 < 0.30 → agreement, no contradiction.
    a = {"value_normalized": 0.50, "normalized_unit": "m/s"}
    b = {"value_normalized": 0.52, "normalized_unit": "m/s"}
    v = detect_contradiction(a, b)
    assert v.is_contradiction is False
    assert v.subtype == "none"
    assert v.likely_correct is None


def test_missing_fields_are_graceful() -> None:
    # Empty dicts → no crash, graceful 'none'.
    v0 = detect_contradiction({}, {})
    assert v0.is_contradiction is False and v0.subtype == "none"
    # Partial CI (only a low bound) is ignored, but the numeric rule still works.
    a = {"value_normalized": 0.2, "normalized_unit": "m/s", "ci_low": 1.0}
    b = {"value_normalized": 0.5, "normalized_unit": "m/s"}
    v1 = detect_contradiction(a, b)
    assert v1.is_contradiction is True
    assert v1.subtype == "numeric_divergence"
    # No evidence / confidence anywhere → likely_correct stays None.
    assert v1.likely_correct is None


def test_classify_pair_and_as_dict() -> None:
    # classify_pair exposes each triggered heuristic, strongest first.
    a = {"value_normalized": 0.2, "normalized_unit": "m/s", "effect_direction": "increase"}
    b = {"value_normalized": 0.5, "normalized_unit": "m/s", "effect_direction": "decrease"}
    findings = classify_pair(a, b)
    assert findings[0][0] == "effect_direction"  # highest priority first
    subtypes = {f[0] for f in findings}
    assert {"effect_direction", "numeric_divergence"} <= subtypes
    # as_dict is a plain JSON-ready mapping with the documented keys.
    d = detect_contradiction(a, b).as_dict()
    assert set(d) == {"is_contradiction", "subtype", "severity", "likely_correct", "reasons"}
    assert d["subtype"] == "effect_direction"
    assert isinstance(d["reasons"], list)

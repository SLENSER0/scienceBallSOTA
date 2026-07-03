"""Tests for the GraphRAG build promotion gate (§11.10 / §11.13)."""

from __future__ import annotations

from kg_retrievers.graphrag_promotion_gate import (
    PromotionDecision,
    evaluate_promotion,
)


def test_clean_build_promotes() -> None:
    d = evaluate_promotion(True, 0.0, 0.9)
    assert d.promote is True
    assert d.blockers == ()


def test_integrity_failure_blocks() -> None:
    d = evaluate_promotion(False, 0.0, 0.9)
    assert d.promote is False
    assert d.blockers == ("integrity_failed",)


def test_unsupported_claims_block_with_default_zero_tolerance() -> None:
    d = evaluate_promotion(True, 0.1, 0.9)
    assert d.promote is False
    assert d.blockers == ("unsupported_claims",)


def test_low_citation_precision_blocks() -> None:
    d = evaluate_promotion(True, 0.0, 0.5)
    assert d.promote is False
    assert d.blockers == ("low_citation_precision",)


def test_all_three_failures_are_ordered() -> None:
    d = evaluate_promotion(False, 0.1, 0.5)
    assert d.promote is False
    assert d.blockers == (
        "integrity_failed",
        "unsupported_claims",
        "low_citation_precision",
    )


def test_citation_precision_exactly_at_min_is_allowed() -> None:
    d = evaluate_promotion(True, 0.0, 0.8)
    assert d.promote is True
    assert d.blockers == ()


def test_unsupported_rate_exactly_at_max_is_allowed() -> None:
    d = evaluate_promotion(True, 0.0, 0.9, max_unsupported=0.0)
    assert d.promote is True


def test_custom_thresholds() -> None:
    # Loosen both bars: a build that would fail defaults now promotes.
    d = evaluate_promotion(True, 0.05, 0.7, max_unsupported=0.1, min_citation_precision=0.6)
    assert d.promote is True
    assert d.blockers == ()


def test_as_dict_promote_is_bool() -> None:
    d = evaluate_promotion(True, 0.0, 0.9)
    out = d.as_dict()
    assert isinstance(out["promote"], bool)
    assert out == {"promote": True, "blockers": ()}


def test_decision_is_frozen() -> None:
    d = PromotionDecision(promote=True, blockers=())
    try:
        d.promote = False  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject assignment
        raise AssertionError("PromotionDecision should be frozen")

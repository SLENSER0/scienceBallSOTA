"""Tests for composite source-trust score & tier — доверие к источнику (§23.27)."""

from __future__ import annotations

import math

import pytest

from kg_common.source_trust_score import TIERS, TrustScore, score_source


def test_retracted_forces_untrusted_regardless_of_inputs() -> None:
    """A retracted source scores 0.0 / tier 'untrusted' even if otherwise ideal."""
    ts = score_source(
        "s1",
        age_days=0.0,
        retracted=True,
        peer_reviewed=True,
        citation_count=10_000,
    )
    assert ts.score == 0.0
    assert ts.tier == "untrusted"
    assert ts.retracted is True


def test_fresh_peer_reviewed_well_cited_is_high() -> None:
    """Age-0, peer-reviewed, many citations → score > 0.67, tier 'high'."""
    ts = score_source(
        "s2",
        age_days=0.0,
        retracted=False,
        peer_reviewed=True,
        citation_count=10_000,
    )
    assert ts.score > 0.67
    assert ts.tier == "high"
    # freshness == 1.0, citation ~= 1.0, peer == 1.0 → raw ~= 1.0.
    assert ts.components["freshness"] == 1.0
    assert ts.components["peer_review"] == 1.0


def test_freshness_component_half_at_half_life() -> None:
    """Freshness component equals 0.5 exactly at age == half_life_days."""
    hl = 1825.0
    ts = score_source(
        "s3",
        age_days=hl,
        retracted=False,
        peer_reviewed=False,
        citation_count=0,
    )
    assert math.isclose(ts.components["freshness"], 0.5, rel_tol=1e-12)


def test_citation_component_zero_and_half() -> None:
    """citation_count 0 → 0.0; count 10 → 0.5 (count/(count+10))."""
    ts0 = score_source(
        "s4",
        age_days=0.0,
        retracted=False,
        peer_reviewed=False,
        citation_count=0,
    )
    ts10 = score_source(
        "s5",
        age_days=0.0,
        retracted=False,
        peer_reviewed=False,
        citation_count=10,
    )
    assert ts0.components["citation"] == 0.0
    assert math.isclose(ts10.components["citation"], 0.5, rel_tol=1e-12)


def test_score_clamped_to_unit_interval() -> None:
    """Every produced score sits within [0, 1]."""
    for age in (0.0, 100.0, 1825.0, 10_000.0):
        for cites in (0, 5, 50, 10_000):
            for peer in (True, False):
                ts = score_source(
                    "s",
                    age_days=age,
                    retracted=False,
                    peer_reviewed=peer,
                    citation_count=cites,
                )
                assert 0.0 <= ts.score <= 1.0


def test_peer_reviewed_false_lowers_score() -> None:
    """Non-peer-reviewed scores strictly below an otherwise-identical reviewed one."""
    common = {"age_days": 100.0, "retracted": False, "citation_count": 25}
    yes = score_source("y", peer_reviewed=True, **common)
    no = score_source("n", peer_reviewed=False, **common)
    assert no.score < yes.score
    # The gap is exactly the peer weight (0.2) since only that component differs.
    assert math.isclose(yes.score - no.score, 0.2, rel_tol=1e-12)


def test_negative_age_raises_value_error() -> None:
    """Negative age_days is rejected — возраст не может быть отрицательным."""
    with pytest.raises(ValueError):
        score_source(
            "s6",
            age_days=-1.0,
            retracted=False,
            peer_reviewed=True,
            citation_count=5,
        )


def test_as_dict_roundtrips_fields() -> None:
    """as_dict() exposes every field as a plain serializable mapping."""
    ts = score_source(
        "s7",
        age_days=0.0,
        retracted=False,
        peer_reviewed=True,
        citation_count=10,
    )
    d = ts.as_dict()
    assert d["source_id"] == "s7"
    assert d["retracted"] is False
    assert d["tier"] in TIERS
    assert set(d["components"]) == {"freshness", "citation", "peer_review"}
    assert isinstance(ts, TrustScore)


def test_tier_bucket_boundaries() -> None:
    """Scores bucket into low (<0.34) / medium (<0.67) / high (>=0.67)."""
    # Old, no citations, no peer review → freshness tiny → low.
    low = score_source(
        "low",
        age_days=20_000.0,
        retracted=False,
        peer_reviewed=False,
        citation_count=0,
    )
    assert low.tier == "low"
    assert low.score < 0.34
    # Fresh, some citations, no peer review → medium band.
    medium = score_source(
        "med",
        age_days=0.0,
        retracted=False,
        peer_reviewed=False,
        citation_count=10,
    )
    # raw = 0.4*1.0 + 0.4*0.5 + 0.2*0 = 0.6 → medium.
    assert math.isclose(medium.score, 0.6, rel_tol=1e-12)
    assert medium.tier == "medium"

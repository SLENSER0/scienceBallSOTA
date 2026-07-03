"""Tests for answer-tier classification of synthesis statements (§24.11)."""

from __future__ import annotations

import pytest

from kg_retrievers.synthesis_tiers import TIERS, TieredStatement, tier_statements


def test_one_per_kind_all_supported() -> None:
    """(1) 4 statements, one per kind, all with evidence → each tier len 1."""
    stmts = [
        {"text": "fact", "kind": "confirmed_fact", "evidence_ids": ["e1"]},
        {"text": "review", "kind": "review_conclusion", "evidence_ids": ["e2"]},
        {"text": "reco", "kind": "recommendation", "evidence_ids": ["e3"]},
        {"text": "hyp", "kind": "hypothesis", "evidence_ids": ["e4"]},
    ]
    out = tier_statements(stmts)
    for tier in TIERS:
        assert len(out[tier]) == 1
    assert out["confirmed_fact"][0].text == "fact"
    assert out["hypothesis"][0].tier == "hypothesis"


def test_unsupported_confirmed_fact_dropped() -> None:
    """(2) A confirmed_fact with empty evidence is dropped, not tiered."""
    stmts = [
        {"text": "no evidence", "kind": "confirmed_fact", "evidence_ids": []},
        {"text": "kept", "kind": "confirmed_fact", "evidence_ids": ["e1"]},
    ]
    out = tier_statements(stmts)
    texts = [s.text for s in out["confirmed_fact"]]
    assert texts == ["kept"]
    assert "no evidence" not in texts


def test_output_always_four_keys() -> None:
    """(3) Output always has exactly the four tier keys."""
    out = tier_statements([])
    assert set(out.keys()) == set(TIERS)
    assert len(out) == 4


def test_unknown_kind_raises() -> None:
    """(4) An unknown 'kind' raises ValueError."""
    with pytest.raises(ValueError, match="unknown statement kind"):
        tier_statements([{"text": "x", "kind": "opinion", "evidence_ids": ["e1"]}])


def test_evidence_deduped_and_n_sources() -> None:
    """(5) evidence_ids are deduped and n_sources matches deduped count."""
    stmts = [
        {
            "text": "dup",
            "kind": "review_conclusion",
            "evidence_ids": ["e1", "e2", "e1", "e2", "e3"],
        }
    ]
    out = tier_statements(stmts)
    tiered = out["review_conclusion"][0]
    assert tiered.evidence_ids == ("e1", "e2", "e3")
    assert tiered.n_sources == 3


def test_input_order_preserved_within_tier() -> None:
    """(6) Statements within a tier preserve input order."""
    stmts = [
        {"text": "b", "kind": "hypothesis", "evidence_ids": ["e1"]},
        {"text": "a", "kind": "hypothesis", "evidence_ids": ["e2"]},
        {"text": "c", "kind": "hypothesis", "evidence_ids": ["e3"]},
    ]
    out = tier_statements(stmts)
    assert [s.text for s in out["hypothesis"]] == ["b", "a", "c"]


def test_as_dict_shape() -> None:
    """(7) as_dict returns tier and a list of evidence_ids."""
    s = TieredStatement(text="t", tier="recommendation", evidence_ids=("e1", "e2"), n_sources=2)
    d = s.as_dict()
    assert d["tier"] == "recommendation"
    assert d["evidence_ids"] == ["e1", "e2"]
    assert isinstance(d["evidence_ids"], list)
    assert d == {
        "text": "t",
        "tier": "recommendation",
        "evidence_ids": ["e1", "e2"],
        "n_sources": 2,
    }


def test_all_unsupported_gives_empty_tuples() -> None:
    """(8) All-unsupported input → all four tuples empty."""
    stmts = [
        {"text": "a", "kind": "confirmed_fact", "evidence_ids": []},
        {"text": "b", "kind": "review_conclusion", "evidence_ids": []},
        {"text": "c", "kind": "recommendation", "evidence_ids": []},
        {"text": "d", "kind": "hypothesis", "evidence_ids": []},
    ]
    out = tier_statements(stmts)
    assert set(out.keys()) == set(TIERS)
    for tier in TIERS:
        assert out[tier] == ()

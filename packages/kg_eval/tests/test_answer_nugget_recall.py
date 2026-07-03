"""Tests for nugget-recall scoring (§23.31)."""

from __future__ import annotations

import pytest

from kg_eval.answer_nugget_recall import NuggetHit, NuggetReport, score_nuggets


def test_all_aliases_present_full_recall() -> None:
    """Answer containing every alias -> recall 1.0, weighted 1.0, no missing."""
    nuggets = [
        {"id": "melting", "aliases": ["melting point"], "weight": 1.0},
        {"id": "phase", "aliases": ["eutectic phase"], "weight": 2.0},
    ]
    answer = "The melting point of the eutectic phase was measured."
    rep = score_nuggets(answer, nuggets)
    assert isinstance(rep, NuggetReport)
    assert rep.n == 2
    assert rep.n_covered == 2
    assert rep.recall == 1.0
    assert rep.weighted_recall == 1.0
    assert rep.missing == ()


def test_none_present_zero_recall_all_missing_sorted() -> None:
    """No alias present -> recall 0.0 and missing == all ids sorted."""
    nuggets = [
        {"id": "zebra", "aliases": ["stripes"]},
        {"id": "apple", "aliases": ["fruit"]},
    ]
    rep = score_nuggets("nothing relevant here", nuggets)
    assert rep.recall == 0.0
    assert rep.n_covered == 0
    assert rep.missing == ("apple", "zebra")
    assert all(not h.covered for h in rep.hits)
    assert all(h.matched_alias is None for h in rep.hits)


def test_case_and_whitespace_insensitive_match() -> None:
    """'Al-Cu' matches inside 'the al-cu alloy' regardless of case/spacing."""
    nuggets = [{"id": "alloy", "aliases": ["Al-Cu"]}]
    rep = score_nuggets("the   al-cu    alloy", nuggets)
    assert rep.recall == 1.0
    assert rep.hits[0].covered is True
    assert rep.hits[0].matched_alias == "Al-Cu"


def test_alias_list_reports_matched_alias() -> None:
    """The specific alias found is reported in matched_alias."""
    nuggets = [{"id": "temp", "aliases": ["absent term", "critical temperature"]}]
    rep = score_nuggets("we observe a critical temperature", nuggets)
    assert rep.hits[0].matched_alias == "critical temperature"
    assert rep.hits[0].covered is True


def test_weighted_recall_differs_from_recall() -> None:
    """weight=3.0 missing, weight=1.0 covered -> recall 0.5, weighted 0.25."""
    nuggets = [
        {"id": "big", "aliases": ["heavy fact"], "weight": 3.0},
        {"id": "small", "aliases": ["light fact"], "weight": 1.0},
    ]
    rep = score_nuggets("only the light fact appears", nuggets)
    assert rep.recall == 0.5
    assert rep.weighted_recall == 0.25
    assert rep.missing == ("big",)


def test_id_used_as_text_when_aliases_empty() -> None:
    """An id used directly as text when aliases empty still matches."""
    nuggets = [{"id": "graphene", "aliases": []}]
    rep = score_nuggets("a sheet of Graphene was grown", nuggets)
    assert rep.recall == 1.0
    assert rep.hits[0].matched_alias == "graphene"


def test_empty_nuggets_raises() -> None:
    """Empty nuggets iterable raises ValueError."""
    with pytest.raises(ValueError):
        score_nuggets("anything", [])


def test_as_dict_lists_hits() -> None:
    """as_dict exposes rounded rates and a list of per-hit dicts."""
    nuggets = [
        {"id": "a", "aliases": ["alpha"], "weight": 3.0},
        {"id": "b", "aliases": ["beta"], "weight": 1.0},
    ]
    rep = score_nuggets("only alpha here", nuggets)
    d = rep.as_dict()
    assert d["n"] == 2
    assert d["n_covered"] == 1
    assert d["recall"] == 0.5
    assert d["weighted_recall"] == 0.75
    assert d["missing"] == ["b"]
    assert isinstance(d["hits"], list) and len(d["hits"]) == 2
    assert d["hits"][0] == {"id": "a", "covered": True, "matched_alias": "alpha"}
    assert d["hits"][1]["covered"] is False


def test_nuggethit_as_dict() -> None:
    """NuggetHit.as_dict round-trips its fields."""
    hit = NuggetHit(id="x", covered=False, matched_alias=None)
    assert hit.as_dict() == {"id": "x", "covered": False, "matched_alias": None}

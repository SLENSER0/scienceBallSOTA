"""Tests for similar-case ranking by feature overlap (§24.12)."""

from __future__ import annotations

from kg_retrievers.similar_cases import CaseSimilarity, rank_similar

_QUERY = {
    "composition": {"Fe": 0.7, "Ni": 0.3},
    "process": "casting",
    "geography": "Russia",
}


def test_identical_case_scores_one_with_all_reasons() -> None:
    case = {"case_id": "c1", **_QUERY}
    (result,) = rank_similar(_QUERY, [case])
    assert result.score == 1.0
    assert set(result.reasons) == {"composition_match", "process_match", "geography_match"}


def test_fully_disjoint_case_scores_zero_no_reasons() -> None:
    case = {
        "case_id": "c1",
        "composition": {"Cu": 1.0},
        "process": "forging",
        "geography": "Japan",
    }
    (result,) = rank_similar(_QUERY, [case])
    assert result.score == 0.0
    assert result.reasons == ()


def test_process_match_geography_differ() -> None:
    case = {
        "case_id": "c1",
        "composition": {"Cu": 1.0},  # disjoint composition
        "process": "casting",  # equal
        "geography": "Japan",  # differ
    }
    (result,) = rank_similar(_QUERY, [case])
    assert "process_match" in result.reasons
    assert "geography_match" not in result.reasons
    assert result.score == 1.0 / 3.0


def test_composition_one_of_two_elements() -> None:
    # query has {Fe, Ni}; case shares only Fe -> union {Fe, Ni}, overlap 1/2.
    case = {
        "case_id": "c1",
        "composition": {"Fe": 1.0},
        "process": "forging",
        "geography": "Japan",
    }
    (result,) = rank_similar(_QUERY, [case])
    assert result.reasons == ("composition_match",)
    assert result.score == 0.5 * (1.0 / 3.0)


def test_results_sorted_descending() -> None:
    strong = {"case_id": "strong", **_QUERY}
    weak = {
        "case_id": "weak",
        "composition": {"Cu": 1.0},
        "process": "forging",
        "geography": "Japan",
    }
    results = rank_similar(_QUERY, [weak, strong])
    assert [r.case_id for r in results] == ["strong", "weak"]
    assert results[0].score >= results[1].score


def test_top_one_returns_single_best() -> None:
    strong = {"case_id": "strong", **_QUERY}
    weak = {
        "case_id": "weak",
        "composition": {"Cu": 1.0},
        "process": "forging",
        "geography": "Japan",
    }
    results = rank_similar(_QUERY, [weak, strong], top=1)
    assert len(results) == 1
    assert results[0].case_id == "strong"


def test_tie_ordered_by_case_id() -> None:
    # Two cases with identical (zero) score -> ascending case_id.
    disjoint = {
        "composition": {"Cu": 1.0},
        "process": "forging",
        "geography": "Japan",
    }
    b = {"case_id": "b", **disjoint}
    a = {"case_id": "a", **disjoint}
    results = rank_similar(_QUERY, [b, a])
    assert [r.case_id for r in results] == ["a", "b"]
    assert results[0].score == results[1].score == 0.0


def test_empty_cases_returns_empty() -> None:
    assert rank_similar(_QUERY, []) == []


def test_as_dict_shape() -> None:
    case = {"case_id": "c1", **_QUERY}
    (result,) = rank_similar(_QUERY, [case])
    assert result.as_dict() == {
        "case_id": "c1",
        "score": 1.0,
        "reasons": list(result.reasons),
    }
    assert isinstance(result, CaseSimilarity)

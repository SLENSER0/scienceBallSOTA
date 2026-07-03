"""Tests for §12.3 Mode B query-term IDF/BM25 weighting."""

from __future__ import annotations

import math

from kg_retrievers.query_term_weighting import (
    WeightedQuery,
    bm25_idf,
    build_weighted_query,
)


def test_rarer_term_weighted_higher() -> None:
    # (1) a rare term (df=1) outweighs a common one (df=9) in a 10-doc corpus.
    assert bm25_idf(1, 10) > bm25_idf(9, 10)


def test_idf_strictly_positive_over_range() -> None:
    # (2) bm25_idf(df, n) > 0 for every 1 <= df <= n.
    for n in (1, 2, 5, 10, 50):
        for df in range(1, n + 1):
            assert bm25_idf(df, n) > 0.0


def test_bm25_idf_matches_formula() -> None:
    # Hand check the exact closed form ln(1 + (N - df + 0.5)/(df + 0.5)).
    assert bm25_idf(1, 10) == math.log(1.0 + (10 - 1 + 0.5) / (1 + 0.5))
    assert bm25_idf(9, 10) == math.log(1.0 + (10 - 9 + 0.5) / (9 + 0.5))


def test_case_folds_and_collapses_duplicates() -> None:
    # (3) 'Steel steel' collapses to a single 'steel' term.
    wq = build_weighted_query("Steel steel", {"steel": 2}, 10)
    assert list(wq.terms) == ["steel"]


def test_stopword_lands_in_dropped_not_terms() -> None:
    # (4) a stopword is dropped, not weighted.
    wq = build_weighted_query(
        "the steel",
        {"steel": 1, "the": 10},
        10,
        stopwords=frozenset({"the"}),
    )
    assert "the" in wq.dropped
    assert "the" not in wq.terms
    assert "steel" in wq.terms


def test_term_below_min_idf_dropped() -> None:
    # (5) a common term whose idf < min_idf is dropped; a rare one survives.
    df_map = {"common": 10, "rare": 1}
    high = bm25_idf(1, 10)
    low = bm25_idf(10, 10)
    threshold = (high + low) / 2.0
    wq = build_weighted_query("common rare", df_map, 10, min_idf=threshold)
    assert "common" in wq.dropped
    assert "common" not in wq.terms
    assert "rare" in wq.terms


def test_unknown_term_treated_as_df_zero_highest_weight() -> None:
    # (6) a term absent from df_map is df=0 -> highest weight, retained.
    df_map = {"steel": 1}
    wq = build_weighted_query("steel novelunknownterm", df_map, 10)
    assert "novelunknownterm" in wq.terms
    assert wq.terms["novelunknownterm"] == bm25_idf(0, 10)
    # df=0 outweighs any 1 <= df <= n term.
    assert wq.terms["novelunknownterm"] > wq.terms["steel"]


def test_kept_weights_strictly_positive() -> None:
    # (7) every kept term carries a strictly positive weight.
    wq = build_weighted_query("steel alumina copper", {"steel": 3, "alumina": 7}, 12)
    assert wq.terms
    for weight in wq.terms.values():
        assert weight > 0.0


def test_as_dict_terms_keys_equal_kept_tokens() -> None:
    # (8) as_dict()['terms'] keys are exactly the kept tokens.
    wq = build_weighted_query(
        "the steel alumina",
        {"steel": 2, "alumina": 5, "the": 12},
        12,
        stopwords=frozenset({"the"}),
    )
    d = wq.as_dict()
    assert set(d["terms"].keys()) == set(wq.terms.keys())
    assert set(d["terms"].keys()) == {"steel", "alumina"}
    assert "the" in d["dropped"]


def test_frozen_dataclass_and_as_dict_shape() -> None:
    wq = WeightedQuery(terms={"steel": 1.5}, dropped=("the",))
    d = wq.as_dict()
    assert d == {"terms": {"steel": 1.5}, "dropped": ["the"]}
    # as_dict returns copies, not the live containers.
    d["terms"]["steel"] = 9.0
    assert wq.terms["steel"] == 1.5

"""Tests for §12.3 Mode B query-specificity predictors.

Hand-checkable idf/SCS assertions with ``N = 100`` so ``log2(100) ≈ 6.6439``.
"""

from __future__ import annotations

import math

import pytest

from kg_retrievers.query_specificity import (
    SpecificityScores,
    predict_specificity,
)

LOG2_100 = math.log2(100)  # ≈ 6.643856


def test_df_one_gives_log2_n() -> None:
    """A term seen in one document out of N earns idf == log2(N)."""
    s = predict_specificity(["rare"], {"rare": 1}, 100)
    assert s.n_terms == 1
    assert s.avg_idf == pytest.approx(LOG2_100)
    assert s.max_idf == pytest.approx(LOG2_100)
    assert s.avg_idf == pytest.approx(6.6439, abs=1e-4)


def test_df_equals_n_gives_zero_idf() -> None:
    """A term present in every document (df == N) has idf == 0."""
    s = predict_specificity(["common"], {"common": 100}, 100)
    assert s.avg_idf == pytest.approx(0.0)
    assert s.max_idf == pytest.approx(0.0)


def test_mixed_rare_and_common_terms() -> None:
    """avg/max idf and SCS over [rare(df=1), common(df=100)] are hand-checked."""
    df_map = {"rare": 1, "common": 100}
    s = predict_specificity(["rare", "common"], df_map, 100)
    assert s.n_terms == 2
    # idf(rare)=6.6439, idf(common)=0.0 → avg = 3.32193
    assert s.avg_idf == pytest.approx(3.3219, abs=1e-4)
    assert s.max_idf == pytest.approx(6.6439, abs=1e-4)
    # scs = -log2(2) + avg = -1.0 + 3.32193
    assert s.scs == pytest.approx(-1.0 + s.avg_idf)
    assert s.scs == pytest.approx(2.3219, abs=1e-4)


def test_unknown_term_defaults_to_df_one() -> None:
    """A term absent from df_map is treated as df=1 (maximally rare)."""
    s = predict_specificity(["ghost"], {}, 100)
    assert s.avg_idf == pytest.approx(LOG2_100)
    assert s.avg_idf == pytest.approx(6.6439, abs=1e-4)


def test_df_below_one_defaults_to_df_one() -> None:
    """A df < 1 in the map is clamped up to df=1 (no divide-by-zero)."""
    s = predict_specificity(["odd"], {"odd": 0}, 100)
    assert s.max_idf == pytest.approx(LOG2_100)


def test_n_terms_counts_distinct_folded_terms() -> None:
    """Duplicates and case/whitespace variants collapse to one distinct term."""
    s = predict_specificity(["Rare", "rare", "  RARE  "], {"rare": 1}, 100)
    assert s.n_terms == 1
    # single distinct term → scs = -log2(1) + avg = 0 + log2(100)
    assert s.scs == pytest.approx(LOG2_100)


def test_empty_terms_all_zero() -> None:
    """An empty query yields all-zero scores."""
    s = predict_specificity([], {"rare": 1}, 100)
    assert s == SpecificityScores(avg_idf=0.0, max_idf=0.0, scs=0.0, n_terms=0)


def test_blank_folds_treated_as_empty() -> None:
    """Terms that fold away to nothing do not count and give zero scores."""
    s = predict_specificity(["   ", ""], {}, 100)
    assert s.n_terms == 0
    assert s.avg_idf == 0.0


def test_as_dict_exposes_all_fields() -> None:
    """as_dict() exposes exactly {avg_idf, max_idf, scs, n_terms}."""
    s = predict_specificity(["rare", "common"], {"rare": 1, "common": 100}, 100)
    d = s.as_dict()
    assert set(d) == {"avg_idf", "max_idf", "scs", "n_terms"}
    assert d["avg_idf"] == pytest.approx(3.3219, abs=1e-4)
    assert d["max_idf"] == pytest.approx(6.6439, abs=1e-4)
    assert d["scs"] == pytest.approx(2.3219, abs=1e-4)
    assert d["n_terms"] == 2


def test_frozen_dataclass_is_immutable() -> None:
    """SpecificityScores is frozen (attributes cannot be reassigned)."""
    s = predict_specificity(["rare"], {"rare": 1}, 100)
    with pytest.raises((AttributeError, TypeError)):
        s.avg_idf = 0.0  # type: ignore[misc]


def test_n_docs_must_be_positive() -> None:
    """A non-positive corpus size is rejected."""
    with pytest.raises(ValueError):
        predict_specificity(["rare"], {"rare": 1}, 0)

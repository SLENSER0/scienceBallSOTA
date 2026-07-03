"""Hand-checkable tests for §7.7 population summary statistics."""

from __future__ import annotations

import pytest

from kg_extractors.measurement_population import (
    PopulationSummary,
    percentile,
    suggest_typical_band,
    summarize_population,
)


def test_summary_central_and_extrema() -> None:
    s = summarize_population([1, 2, 3, 4, 5])
    assert s.mean == 3.0
    assert s.median == 3.0
    assert s.minimum == 1.0
    assert s.maximum == 5.0
    assert s.n == 5


def test_percentile_linear_interpolation() -> None:
    # sorted [1,2,3,4], rank = 3*0.5 = 1.5 → between 2 and 3 → 2.5
    assert percentile([1, 2, 3, 4], 50) == 2.5


def test_percentile_zero_returns_minimum() -> None:
    assert percentile([10, 20, 30], 0) == 10


def test_percentile_hundred_returns_maximum() -> None:
    assert percentile([10, 20, 30], 100) == 30


def test_percentile_unsorted_input() -> None:
    # order must not matter — coerced then sorted internally
    assert percentile([4, 1, 3, 2], 50) == 2.5


def test_single_value_stdev_zero() -> None:
    assert summarize_population([7]).stdev == 0.0


def test_single_value_percentiles_and_extrema() -> None:
    s = summarize_population([7])
    assert s.p05 == 7.0
    assert s.p95 == 7.0
    assert s.minimum == 7.0 == s.maximum


def test_empty_population_raises() -> None:
    with pytest.raises(ValueError):
        summarize_population([])


def test_empty_percentile_raises() -> None:
    with pytest.raises(ValueError):
        percentile([], 50)


def test_percentile_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        percentile([1, 2, 3], 150)


def test_band_excludes_high_outlier() -> None:
    lo, hi = suggest_typical_band([10, 11, 12, 13, 14, 100])
    assert hi < 100  # the 100 sits outside the Tukey fence
    assert lo < 10  # band brackets the dense cluster


def test_band_hand_computed_fence() -> None:
    # sorted [10,11,12,13,14,100]: Q1 = 11.25, Q3 = 13.75, IQR = 2.5
    # hi = 13.75 + 1.5*2.5 = 17.5 ; lo = 11.25 - 1.5*2.5 = 7.5
    lo, hi = suggest_typical_band([10, 11, 12, 13, 14, 100])
    assert lo == pytest.approx(7.5)
    assert hi == pytest.approx(17.5)


def test_band_widening_k() -> None:
    narrow = suggest_typical_band([1, 2, 3, 4, 5], k=1.5)
    wide = suggest_typical_band([1, 2, 3, 4, 5], k=3.0)
    assert wide[0] < narrow[0]
    assert wide[1] > narrow[1]


def test_band_single_value() -> None:
    assert suggest_typical_band([42]) == (42.0, 42.0)


def test_band_empty_raises() -> None:
    with pytest.raises(ValueError):
        suggest_typical_band([])


def test_unit_roundtrips_through_as_dict() -> None:
    assert summarize_population([1, 2, 3], unit="MPa").as_dict()["unit"] == "MPa"


def test_unit_defaults_to_none() -> None:
    assert summarize_population([1, 2, 3]).unit is None


def test_as_dict_has_all_fields() -> None:
    d = summarize_population([1, 2, 3, 4, 5], unit="GPa").as_dict()
    assert set(d) == {
        "n",
        "mean",
        "median",
        "stdev",
        "p05",
        "p95",
        "minimum",
        "maximum",
        "unit",
    }
    assert d["n"] == 5


def test_non_numeric_entries_skipped() -> None:
    # "not a number" and None dropped; "2,5" (comma decimal) coerced to 2.5
    s = summarize_population([1, "not a number", None, "2,5", 3])
    assert s.n == 3
    assert s.minimum == 1.0
    assert s.maximum == 3.0


def test_bool_is_not_numeric() -> None:
    # bool is an int subclass but must be rejected, not counted as 1/0
    assert summarize_population([1, True, 2, False, 3]).n == 3


def test_summary_is_frozen() -> None:
    import dataclasses

    s = summarize_population([1, 2, 3])
    assert isinstance(s, PopulationSummary)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.n = 99  # type: ignore[misc]


def test_stdev_matches_sample_formula() -> None:
    import statistics as _st

    s = summarize_population([2, 4, 4, 4, 5, 5, 7, 9])
    assert s.stdev == pytest.approx(_st.stdev([2, 4, 4, 4, 5, 5, 7, 9]))

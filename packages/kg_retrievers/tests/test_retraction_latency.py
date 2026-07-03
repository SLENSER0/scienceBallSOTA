"""Tests for retraction latency — время до ретракции (§25.12).

Hand-checkable: fixed ISO dates, known day-count arithmetic and buckets.
"""

from __future__ import annotations

from kg_retrievers.retraction_latency import (
    RetractionLatencyReport,
    _days_between,
    retraction_latency,
)


def test_single_30_day_latency_and_bucket() -> None:
    """Published 2020-01-01, retracted 2020-01-31 -> 30.0 days, bucket ``<=30``."""
    obs = [{"retracted": True, "published_at": "2020-01-01", "retracted_at": "2020-01-31"}]
    rep = retraction_latency(obs)
    assert rep.n_retracted == 1
    assert rep.n_with_dates == 1
    assert rep.latencies_days == (30.0,)
    assert rep.buckets["<=30"] == 1
    assert rep.min_days == 30.0
    assert rep.max_days == 30.0


def test_400_day_case_lands_in_over_365_bucket() -> None:
    """A 400-day latency falls into the ``>365`` band."""
    # 2020-01-01 + 400 days = 2021-02-04
    obs = [{"retracted": True, "published_at": "2020-01-01", "retracted_at": "2021-02-04"}]
    rep = retraction_latency(obs)
    assert rep.latencies_days == (400.0,)
    assert rep.buckets[">365"] == 1
    assert rep.buckets["<=30"] == 0


def test_mean_of_30_and_200_is_115() -> None:
    """Mean of latencies [30, 200] == 115.0."""
    obs = [
        {"retracted": True, "published_at": "2020-01-01", "retracted_at": "2020-01-31"},
        {"retracted": True, "published_at": "2020-01-01", "retracted_at": "2020-07-19"},
    ]
    rep = retraction_latency(obs)
    assert rep.latencies_days == (30.0, 200.0)
    assert rep.mean_days == 115.0
    assert rep.buckets["<=30"] == 1
    assert rep.buckets["31-180"] == 0
    assert rep.buckets["181-365"] == 1


def test_median_of_10_30_400_is_30() -> None:
    """Median of latencies [10, 30, 400] == 30.0."""
    obs = [
        {"retracted": True, "published_at": "2020-01-01", "retracted_at": "2020-01-11"},
        {"retracted": True, "published_at": "2020-01-01", "retracted_at": "2020-01-31"},
        {"retracted": True, "published_at": "2020-01-01", "retracted_at": "2021-02-04"},
    ]
    rep = retraction_latency(obs)
    assert rep.latencies_days == (10.0, 30.0, 400.0)
    assert rep.median_days == 30.0


def test_non_retracted_excluded_from_n_retracted() -> None:
    """An observation without a truthy ``retracted`` prop is not counted."""
    obs = [
        {"retracted": False, "published_at": "2020-01-01", "retracted_at": "2020-01-31"},
        {"published_at": "2020-01-01", "retracted_at": "2020-01-31"},
    ]
    rep = retraction_latency(obs)
    assert rep.n_retracted == 0
    assert rep.n_with_dates == 0
    assert rep.latencies_days == ()


def test_retracted_missing_date_counts_but_no_latency() -> None:
    """Retracted but missing ``retracted_at``: counts in n_retracted, adds no latency."""
    obs = [{"retracted": True, "published_at": "2020-01-01"}]
    rep = retraction_latency(obs)
    assert rep.n_retracted == 1
    assert rep.n_with_dates == 0
    assert rep.latencies_days == ()
    assert all(v == 0 for v in rep.buckets.values())


def test_empty_input_all_none_and_zero_buckets() -> None:
    """Empty input -> all ``*_days`` None and every bucket 0."""
    rep = retraction_latency([])
    assert rep.n_retracted == 0
    assert rep.n_with_dates == 0
    assert rep.latencies_days == ()
    assert rep.min_days is None
    assert rep.median_days is None
    assert rep.mean_days is None
    assert rep.max_days is None
    assert rep.buckets == {"<=30": 0, "31-180": 0, "181-365": 0, ">365": 0}


def test_as_dict_latencies_is_a_list() -> None:
    """``as_dict()['latencies_days']`` is a list, not a tuple."""
    obs = [{"retracted": True, "published_at": "2020-01-01", "retracted_at": "2020-01-31"}]
    d = retraction_latency(obs).as_dict()
    assert isinstance(d["latencies_days"], list)
    assert d["latencies_days"] == [30.0]
    assert d["buckets"] == {"<=30": 1, "31-180": 0, "181-365": 0, ">365": 0}


def test_days_between_reversed_and_missing_return_none() -> None:
    """Reversed interval or a missing endpoint -> None."""
    assert _days_between("2020-01-31", "2020-01-01") is None  # reversed
    assert _days_between("", "2020-01-01") is None  # missing published
    assert _days_between("2020-01-01", "") is None  # missing retracted
    assert _days_between("not-a-date", "2020-01-01") is None  # unparseable
    assert _days_between("2020-01-01", "2020-01-31") == 30.0


def test_report_is_frozen() -> None:
    """RetractionLatencyReport is a frozen dataclass (immutable)."""
    rep = retraction_latency([])
    try:
        rep.n_retracted = 5  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("expected frozen dataclass to reject attribute assignment")


def test_report_type() -> None:
    """Return value is a RetractionLatencyReport."""
    assert isinstance(retraction_latency([]), RetractionLatencyReport)

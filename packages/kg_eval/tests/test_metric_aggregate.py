"""Per-metric aggregation across repeated eval runs (§18.12)."""

from __future__ import annotations

from math import sqrt

from pytest import approx

from kg_eval.metric_aggregate import MetricAggregate, aggregate_metrics


def test_mean_min_max_n_exact() -> None:
    # f1 across three runs: 0.2, 0.4, 0.9 -> mean 0.5, min 0.2, max 0.9, n 3
    agg = aggregate_metrics([{"f1": 0.2}, {"f1": 0.4}, {"f1": 0.9}])
    a = agg["f1"]
    assert a.mean == approx(0.5)
    assert a.min == approx(0.2)
    assert a.max == approx(0.9)
    assert a.n == 3


def test_std_population_hand_value() -> None:
    # values 1, 2, 3, 4 -> mean 2.5, population variance = 5/4 = 1.25
    agg = aggregate_metrics([{"m": 1.0}, {"m": 2.0}, {"m": 3.0}, {"m": 4.0}])
    a = agg["m"]
    assert a.mean == approx(2.5)
    assert a.std == approx(sqrt(1.25))  # ~1.118033988...


def test_per_key_independent() -> None:
    agg = aggregate_metrics(
        [
            {"precision": 0.8, "recall": 0.6},
            {"precision": 0.6, "recall": 0.2},
        ]
    )
    assert set(agg) == {"precision", "recall"}
    assert agg["precision"].mean == approx(0.7)
    assert agg["precision"].min == approx(0.6)
    assert agg["precision"].max == approx(0.8)
    assert agg["recall"].mean == approx(0.4)
    assert agg["recall"].min == approx(0.2)
    assert agg["recall"].max == approx(0.6)


def test_single_run_std_zero() -> None:
    agg = aggregate_metrics([{"f1": 0.73}])
    a = agg["f1"]
    assert a.std == 0.0
    assert a.mean == approx(0.73)
    assert a.min == approx(0.73)
    assert a.max == approx(0.73)
    assert a.n == 1


def test_empty_runs_is_empty_mapping() -> None:
    assert aggregate_metrics([]) == {}


def test_missing_key_counted_only_where_present() -> None:
    # "recall" only appears in two of three runs -> n == 2 for it
    agg = aggregate_metrics(
        [
            {"precision": 0.5, "recall": 0.4},
            {"precision": 0.7},
            {"precision": 0.9, "recall": 0.8},
        ]
    )
    assert agg["precision"].n == 3
    assert agg["precision"].mean == approx(0.7)
    assert agg["recall"].n == 2
    assert agg["recall"].mean == approx(0.6)
    assert agg["recall"].min == approx(0.4)
    assert agg["recall"].max == approx(0.8)


def test_key_absent_everywhere_is_omitted() -> None:
    agg = aggregate_metrics([{"a": 1.0}, {"a": 2.0}])
    assert "b" not in agg
    assert set(agg) == {"a"}


def test_as_dict_shape_and_values() -> None:
    agg = aggregate_metrics([{"m": 1.0}, {"m": 2.0}, {"m": 3.0}, {"m": 4.0}])
    d = agg["m"].as_dict()
    assert d == {
        "mean": 2.5,
        "std": round(sqrt(1.25), 6),
        "min": 1.0,
        "max": 4.0,
        "n": 4,
    }


def test_as_dict_keys() -> None:
    d = aggregate_metrics([{"m": 5.0}])["m"].as_dict()
    assert set(d) == {"mean", "std", "min", "max", "n"}


def test_frozen_dataclass_immutable() -> None:
    a = MetricAggregate(mean=1.0, std=0.0, min=1.0, max=1.0, n=1)
    try:
        a.mean = 2.0  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("MetricAggregate must be frozen")

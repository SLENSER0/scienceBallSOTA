"""Baseline/ablation benchmark: N-system per-metric winner table (§23.31)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_eval.baseline_benchmark import (
    BenchmarkComparison,
    MetricRow,
    compare,
)


def _systems() -> dict[str, dict[str, float]]:
    # full beats every baseline on recall (higher-better) and latency (lower-better).
    return {
        "full": {"recall": 0.90, "latency_ms": 100.0},
        "baseline_a": {"recall": 0.80, "latency_ms": 150.0},
        "baseline_b": {"recall": 0.85, "latency_ms": 200.0},
    }


def test_higher_is_better_winner_is_max() -> None:
    # recall: max score 0.90 belongs to "full".
    cmp = compare(_systems(), full_system="full", directions={"recall": True, "latency_ms": False})
    row = next(m for m in cmp.metrics if m.metric == "recall")
    assert row.higher_is_better is True
    assert row.winner == "full"


def test_lower_is_better_winner_is_min() -> None:
    # latency: min score 100.0 belongs to "full".
    cmp = compare(_systems(), full_system="full", directions={"recall": True, "latency_ms": False})
    row = next(m for m in cmp.metrics if m.metric == "latency_ms")
    assert row.higher_is_better is False
    assert row.winner == "full"


def test_full_delta_positive_when_full_beats_best_higher_is_better() -> None:
    # recall: full 0.90 - best baseline 0.85 = +0.05.
    cmp = compare(_systems(), full_system="full", directions={"recall": True})
    row = cmp.metrics[0]
    assert row.metric == "recall"
    assert row.full_delta == pytest.approx(0.05)
    assert row.full_delta > 0.0


def test_full_delta_positive_when_full_beats_best_lower_is_better() -> None:
    # latency: best baseline 150.0 - full 100.0 = +50.0 (sign-adjusted → full wins).
    cmp = compare(_systems(), full_system="full", directions={"latency_ms": False})
    row = cmp.metrics[0]
    assert row.metric == "latency_ms"
    assert row.full_delta == pytest.approx(50.0)
    assert row.full_delta > 0.0


def test_full_delta_negative_when_full_loses() -> None:
    # full has worse recall than a baseline → delta negative → a loss.
    systems = {
        "full": {"recall": 0.70},
        "baseline_a": {"recall": 0.90},
    }
    cmp = compare(systems, full_system="full", directions={"recall": True})
    row = cmp.metrics[0]
    assert row.full_delta == pytest.approx(-0.20)
    assert cmp.full_losses == 1
    assert cmp.full_wins == 0


def test_winner_tie_resolves_to_lexicographically_smallest() -> None:
    # "aaa" and "zzz" both top recall at 0.90 → winner is the smaller name.
    systems = {
        "zzz": {"recall": 0.90},
        "aaa": {"recall": 0.90},
        "full": {"recall": 0.50},
    }
    cmp = compare(systems, full_system="full", directions={"recall": True})
    assert cmp.metrics[0].winner == "aaa"


def test_verdict_sota_when_full_wins_majority() -> None:
    # full wins recall + latency (2), loses cost (1) → 2 > 1 → "sota".
    systems = {
        "full": {"recall": 0.90, "latency_ms": 100.0, "cost": 5.0},
        "baseline_a": {"recall": 0.80, "latency_ms": 150.0, "cost": 2.0},
    }
    cmp = compare(
        systems,
        full_system="full",
        directions={"recall": True, "latency_ms": False, "cost": False},
    )
    assert cmp.full_wins == 2
    assert cmp.full_losses == 1
    assert cmp.verdict == "sota"


def test_verdict_not_sota_when_full_does_not_win_majority() -> None:
    # full wins recall (1), loses latency + cost (2) → not majority → "not_sota".
    systems = {
        "full": {"recall": 0.90, "latency_ms": 300.0, "cost": 9.0},
        "baseline_a": {"recall": 0.80, "latency_ms": 150.0, "cost": 2.0},
    }
    cmp = compare(
        systems,
        full_system="full",
        directions={"recall": True, "latency_ms": False, "cost": False},
    )
    assert cmp.full_wins == 1
    assert cmp.full_losses == 2
    assert cmp.verdict == "not_sota"


def test_tie_counts_in_neither_wins_nor_losses() -> None:
    # full ties the sole baseline on recall → 0 wins, 0 losses, 1 tie.
    systems = {
        "full": {"recall": 0.80},
        "baseline_a": {"recall": 0.80},
    }
    cmp = compare(systems, full_system="full", directions={"recall": True})
    assert cmp.full_wins == 0
    assert cmp.full_losses == 0
    assert cmp.metrics[0].full_delta == 0.0
    assert cmp.verdict == "not_sota"


def test_wins_plus_losses_plus_ties_equals_metric_count() -> None:
    systems = {
        "full": {"recall": 0.90, "latency_ms": 100.0, "cost": 5.0, "f1": 0.5},
        "baseline_a": {"recall": 0.80, "latency_ms": 150.0, "cost": 2.0, "f1": 0.5},
    }
    directions = {"recall": True, "latency_ms": False, "cost": False, "f1": True}
    cmp = compare(systems, full_system="full", directions=directions)
    ties = len(cmp.metrics) - cmp.full_wins - cmp.full_losses
    assert cmp.full_wins + cmp.full_losses + ties == len(cmp.metrics)
    assert ties == 1  # f1 is tied


def test_missing_metric_for_a_system_raises_keyerror() -> None:
    systems = {
        "full": {"recall": 0.90, "latency_ms": 100.0},
        "baseline_a": {"recall": 0.80},  # no latency_ms
    }
    with pytest.raises(KeyError):
        compare(
            systems,
            full_system="full",
            directions={"recall": True, "latency_ms": False},
        )


def test_unknown_full_system_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        compare(_systems(), full_system="ghost", directions={"recall": True})


def test_metrics_sorted_by_name_for_determinism() -> None:
    cmp = compare(
        _systems(),
        full_system="full",
        directions={"recall": True, "latency_ms": False},
    )
    names = [m.metric for m in cmp.metrics]
    assert names == sorted(names)
    assert names == ["latency_ms", "recall"]


def test_scores_sorted_by_system_name() -> None:
    cmp = compare(_systems(), full_system="full", directions={"recall": True})
    systems_in_row = [s for s, _ in cmp.metrics[0].scores]
    assert systems_in_row == sorted(systems_in_row)
    assert systems_in_row == ["baseline_a", "baseline_b", "full"]


def test_as_dict_metrics_is_list_of_dicts() -> None:
    cmp = compare(
        _systems(),
        full_system="full",
        directions={"recall": True, "latency_ms": False},
    )
    d = cmp.as_dict()
    assert isinstance(d["metrics"], list)
    assert all(isinstance(m, dict) for m in d["metrics"])
    first = d["metrics"][0]
    assert set(first) == {"metric", "higher_is_better", "scores", "winner", "full_delta"}
    assert isinstance(first["scores"], list)
    assert d["verdict"] in {"sota", "not_sota"}
    assert d["full_system"] == "full"


def test_frozen_dataclasses() -> None:
    cmp = compare(_systems(), full_system="full", directions={"recall": True})
    with pytest.raises(dataclasses.FrozenInstanceError):
        cmp.verdict = "x"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        cmp.metrics[0].winner = "x"  # type: ignore[misc]
    assert isinstance(cmp, BenchmarkComparison)
    assert isinstance(cmp.metrics[0], MetricRow)

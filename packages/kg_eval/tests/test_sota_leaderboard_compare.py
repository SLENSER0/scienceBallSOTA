"""SOTA leaderboard compare: ours vs published external SOTA numbers (§23.31/§23.35)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_eval.sota_leaderboard_compare import (
    SotaComparison,
    SotaRow,
    compare,
)


def test_higher_is_better_delta_and_beats() -> None:
    # ours 0.90 vs LightRAG 0.82 (higher-is-better) → delta 0.08, beats True.
    cmp = compare({"recall": 0.90}, {"recall": ("LightRAG", 0.82)})
    row = cmp.rows[0]
    assert row.delta == pytest.approx(0.08)
    assert row.beats is True
    assert row.external_system == "LightRAG"


def test_lower_is_better_delta_and_beats() -> None:
    # latency ours 100 vs external 120 (lower-is-better) → delta 20, beats True.
    cmp = compare(
        {"latency_ms": 100.0},
        {"latency_ms": ("olmOCR", 120.0)},
        higher_is_better={"latency_ms": False},
    )
    row = cmp.rows[0]
    assert row.delta == pytest.approx(20.0)
    assert row.beats is True


def test_tie_counts_as_beats() -> None:
    # equal values → delta 0.0 → beats True (>=0).
    cmp = compare({"f1": 0.75}, {"f1": ("SomeSystem", 0.75)})
    row = cmp.rows[0]
    assert row.delta == 0.0
    assert row.beats is True


def test_losing_metric_beats_false() -> None:
    # ours 0.70 < external 0.90 (higher-is-better) → delta -0.20 → beats False.
    cmp = compare({"recall": 0.70}, {"recall": ("LightRAG", 0.90)})
    row = cmp.rows[0]
    assert row.delta == pytest.approx(-0.20)
    assert row.beats is False


def test_verdict_competitive_when_majority_beaten() -> None:
    # 3 metrics, 2 beaten (recall, latency), 1 lost (cost) → 2 >= 2 → competitive.
    ours = {"recall": 0.90, "latency_ms": 100.0, "cost": 9.0}
    external = {
        "recall": ("LightRAG", 0.82),
        "latency_ms": ("olmOCR", 120.0),
        "cost": ("olmOCR", 5.0),
    }
    cmp = compare(
        ours,
        external,
        higher_is_better={"recall": True, "latency_ms": False, "cost": False},
    )
    assert cmp.n_beat == 2
    assert cmp.verdict == "competitive"


def test_verdict_behind_when_only_one_of_three_beaten() -> None:
    # 3 metrics, only recall beaten (1) → 1 < 2 → behind.
    ours = {"recall": 0.90, "latency_ms": 300.0, "cost": 9.0}
    external = {
        "recall": ("LightRAG", 0.82),
        "latency_ms": ("olmOCR", 120.0),
        "cost": ("olmOCR", 5.0),
    }
    cmp = compare(
        ours,
        external,
        higher_is_better={"recall": True, "latency_ms": False, "cost": False},
    )
    assert cmp.n_beat == 1
    assert cmp.verdict == "behind"


def test_external_system_name_carried_into_row() -> None:
    cmp = compare(
        {"recall": 0.9, "teds": 0.8},
        {"recall": ("LightRAG", 0.82), "teds": ("olmOCR-Bench", 0.79)},
    )
    by_metric = {r.metric: r.external_system for r in cmp.rows}
    assert by_metric == {"recall": "LightRAG", "teds": "olmOCR-Bench"}


def test_rows_sorted_by_metric_name() -> None:
    cmp = compare(
        {"recall": 0.9, "accuracy": 0.8, "teds": 0.7},
        {
            "recall": ("A", 0.5),
            "accuracy": ("B", 0.5),
            "teds": ("C", 0.5),
        },
    )
    names = [r.metric for r in cmp.rows]
    assert names == sorted(names)
    assert names == ["accuracy", "recall", "teds"]


def test_as_dict_nests_rows_as_list_of_dicts() -> None:
    cmp = compare({"recall": 0.9}, {"recall": ("LightRAG", 0.82)})
    d = cmp.as_dict()
    assert isinstance(d["rows"], list)
    assert all(isinstance(r, dict) for r in d["rows"])
    first = d["rows"][0]
    assert set(first) == {"metric", "ours", "external", "external_system", "delta", "beats"}
    assert d["n_beat"] == 1
    assert d["verdict"] == "competitive"


def test_missing_our_metric_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        compare({"recall": 0.9}, {"latency_ms": ("olmOCR", 120.0)})


def test_metric_without_external_is_skipped() -> None:
    # ours has an extra metric with no external number → not in rows.
    cmp = compare({"recall": 0.9, "spare": 0.1}, {"recall": ("LightRAG", 0.82)})
    assert [r.metric for r in cmp.rows] == ["recall"]


def test_empty_comparison_is_trivially_competitive() -> None:
    cmp = compare({}, {})
    assert cmp.rows == ()
    assert cmp.n_beat == 0
    assert cmp.verdict == "competitive"


def test_frozen_dataclasses() -> None:
    cmp = compare({"recall": 0.9}, {"recall": ("LightRAG", 0.82)})
    with pytest.raises(dataclasses.FrozenInstanceError):
        cmp.verdict = "x"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        cmp.rows[0].beats = False  # type: ignore[misc]
    assert isinstance(cmp, SotaComparison)
    assert isinstance(cmp.rows[0], SotaRow)

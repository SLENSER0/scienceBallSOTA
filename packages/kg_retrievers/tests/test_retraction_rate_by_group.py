"""Tests for per-group retraction rate — доля ретракций по группам (§25.12)."""

from __future__ import annotations

from kg_retrievers.retraction_rate_by_group import (
    MISSING_GROUP,
    GroupRetractionRate,
    RetractionRateReport,
    retraction_rate_by_group,
)


def _obs(domain: str, retracted: bool = False) -> dict:
    return {"domain": domain, "retracted": retracted}


def test_group_of_four_with_one_retracted_has_rate_quarter() -> None:
    obs = [
        _obs("X"),
        _obs("X"),
        _obs("X"),
        _obs("X", retracted=True),
    ]
    report = retraction_rate_by_group(obs)
    (x,) = report.groups
    assert x.group == "X"
    assert x.n == 4
    assert x.n_retracted == 1
    assert x.rate == 0.25


def test_overall_rate_is_total_retracted_over_total() -> None:
    obs = [
        _obs("A", retracted=True),
        _obs("A"),
        _obs("B", retracted=True),
        _obs("B", retracted=True),
        _obs("C"),
    ]
    report = retraction_rate_by_group(obs)
    assert report.overall_rate == 3 / 5


def test_group_with_no_retracted_has_zero_rate() -> None:
    obs = [_obs("clean"), _obs("clean"), _obs("clean")]
    report = retraction_rate_by_group(obs)
    (clean,) = report.groups
    assert clean.n_retracted == 0
    assert clean.rate == 0.0


def test_worst_first_is_highest_rate_group() -> None:
    obs = [
        _obs("low"),
        _obs("low"),
        _obs("low", retracted=True),  # rate 1/3
        _obs("high", retracted=True),
        _obs("high"),  # rate 1/2
    ]
    report = retraction_rate_by_group(obs)
    assert report.worst[0].group == "high"
    assert report.worst[0].rate == 0.5


def test_missing_group_key_bucketed_under_em_dash() -> None:
    obs = [
        {"retracted": True},
        {"domain": None, "retracted": False},
        _obs("named"),
    ]
    report = retraction_rate_by_group(obs)
    by_group = {g.group: g for g in report.groups}
    assert MISSING_GROUP in by_group
    assert by_group[MISSING_GROUP].n == 2
    assert by_group[MISSING_GROUP].n_retracted == 1


def test_tie_on_rate_sorts_alphabetically() -> None:
    obs = [
        _obs("zebra", retracted=True),
        _obs("apple", retracted=True),
    ]
    report = retraction_rate_by_group(obs)
    # both rate 1.0 -> alphabetical
    assert [g.group for g in report.worst] == ["apple", "zebra"]


def test_empty_input_gives_zero_overall_and_no_groups() -> None:
    report = retraction_rate_by_group([])
    assert report.overall_rate == 0.0
    assert report.groups == ()
    assert report.worst == ()


def test_top_n_caps_worst_list() -> None:
    obs = [_obs(g, retracted=True) for g in ("a", "b", "c", "d", "e", "f")]
    report = retraction_rate_by_group(obs, top_n=3)
    assert len(report.worst) == 3
    assert len(report.groups) == 6


def test_custom_group_key() -> None:
    obs = [
        {"source": "s1", "retracted": True},
        {"source": "s1", "retracted": False},
        {"source": "s2", "retracted": False},
    ]
    report = retraction_rate_by_group(obs, group_key="source")
    by_group = {g.group: g for g in report.groups}
    assert by_group["s1"].rate == 0.5
    assert by_group["s2"].rate == 0.0


def test_as_dict_round_trips_worst_as_list() -> None:
    obs = [_obs("A", retracted=True), _obs("B")]
    report = retraction_rate_by_group(obs)
    d = report.as_dict()
    assert isinstance(d["worst"], list)
    assert isinstance(d["groups"], list)
    assert d["worst"][0] == {"group": "A", "n": 1, "n_retracted": 1, "rate": 1.0}
    assert d["overall_rate"] == 0.5


def test_frozen_dataclasses() -> None:
    gr = GroupRetractionRate(group="g", n=2, n_retracted=1, rate=0.5)
    assert gr.as_dict() == {"group": "g", "n": 2, "n_retracted": 1, "rate": 0.5}
    rep = RetractionRateReport(groups=(gr,), overall_rate=0.5, worst=(gr,))
    assert rep.as_dict()["overall_rate"] == 0.5

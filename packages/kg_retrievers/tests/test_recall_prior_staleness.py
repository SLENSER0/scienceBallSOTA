"""Tests for the recall-prior staleness detector (§25.10)."""

from __future__ import annotations

from kg_retrievers.recall_prior_staleness import (
    REASON_BOTH,
    REASON_EXTRACTOR,
    REASON_PARSER,
    StalenessReport,
    StalePrior,
    find_stale_priors,
)

CURRENT_PARSER = "p2"
CURRENT_EXTRACTOR = "e2"


def _prior(key: str, parser: str, extractor: str) -> dict:
    """Build a raw prior dict."""
    return {
        "context_key": key,
        "parser_version": parser,
        "extractor_version": extractor,
    }


def test_matching_both_is_fresh() -> None:
    """A prior matching both current versions is fresh, not stale."""
    report = find_stale_priors(
        [_prior("k", CURRENT_PARSER, CURRENT_EXTRACTOR)],
        CURRENT_PARSER,
        CURRENT_EXTRACTOR,
    )
    assert report.n_stale == 0
    assert report.n_fresh == 1
    assert report.fresh == ["k"]
    assert report.stale == []


def test_old_parser_only_reason() -> None:
    """Only an old parser version yields reason ``parser_outdated``."""
    report = find_stale_priors(
        [_prior("k", "p1", CURRENT_EXTRACTOR)],
        CURRENT_PARSER,
        CURRENT_EXTRACTOR,
    )
    assert report.n_stale == 1
    assert report.stale[0] == StalePrior(context_key="k", reason=REASON_PARSER)
    assert report.stale[0].reason == "parser_outdated"


def test_old_extractor_only_reason() -> None:
    """Only an old extractor version yields reason ``extractor_outdated``."""
    report = find_stale_priors(
        [_prior("k", CURRENT_PARSER, "e1")],
        CURRENT_PARSER,
        CURRENT_EXTRACTOR,
    )
    assert report.n_stale == 1
    assert report.stale[0].reason == REASON_EXTRACTOR
    assert report.stale[0].reason == "extractor_outdated"


def test_both_old_reason() -> None:
    """Both versions old yields reason ``both``."""
    report = find_stale_priors(
        [_prior("k", "p1", "e1")],
        CURRENT_PARSER,
        CURRENT_EXTRACTOR,
    )
    assert report.stale[0].reason == REASON_BOTH
    assert report.stale[0].reason == "both"


def test_stale_fraction_definition() -> None:
    """``stale_fraction`` equals ``n_stale / (n_stale + n_fresh)``."""
    priors = [
        _prior("fresh1", CURRENT_PARSER, CURRENT_EXTRACTOR),
        _prior("fresh2", CURRENT_PARSER, CURRENT_EXTRACTOR),
        _prior("stale1", "p1", CURRENT_EXTRACTOR),
        _prior("stale2", CURRENT_PARSER, "e1"),
    ]
    report = find_stale_priors(priors, CURRENT_PARSER, CURRENT_EXTRACTOR)
    assert report.n_stale == 2
    assert report.n_fresh == 2
    assert report.stale_fraction == report.n_stale / (report.n_stale + report.n_fresh)
    assert report.stale_fraction == 0.5


def test_empty_priors_no_division_error() -> None:
    """Empty priors give ``stale_fraction`` 0.0 without a division error."""
    report = find_stale_priors([], CURRENT_PARSER, CURRENT_EXTRACTOR)
    assert report.n_stale == 0
    assert report.n_fresh == 0
    assert report.stale_fraction == 0.0
    assert report.stale == []
    assert report.fresh == []


def test_fresh_list_holds_context_keys() -> None:
    """The fresh list holds the ``context_key``s of matching priors."""
    priors = [
        _prior("a", CURRENT_PARSER, CURRENT_EXTRACTOR),
        _prior("b", "p1", "e1"),
        _prior("c", CURRENT_PARSER, CURRENT_EXTRACTOR),
    ]
    report = find_stale_priors(priors, CURRENT_PARSER, CURRENT_EXTRACTOR)
    assert report.fresh == ["a", "c"]


def test_counts_partition_input() -> None:
    """``n_stale + n_fresh`` equals the number of input priors."""
    priors = [
        _prior("a", CURRENT_PARSER, CURRENT_EXTRACTOR),
        _prior("b", "p1", CURRENT_EXTRACTOR),
        _prior("c", CURRENT_PARSER, "e1"),
        _prior("d", "p1", "e1"),
        _prior("e", CURRENT_PARSER, CURRENT_EXTRACTOR),
    ]
    report = find_stale_priors(priors, CURRENT_PARSER, CURRENT_EXTRACTOR)
    assert report.n_stale + report.n_fresh == len(priors)


def test_as_dict_round_trip() -> None:
    """``as_dict`` on report and stale prior exposes all fields."""
    priors = [
        _prior("a", CURRENT_PARSER, CURRENT_EXTRACTOR),
        _prior("b", "p1", "e1"),
    ]
    report = find_stale_priors(priors, CURRENT_PARSER, CURRENT_EXTRACTOR)
    assert isinstance(report, StalenessReport)
    d = report.as_dict()
    assert d["n_stale"] == 1
    assert d["n_fresh"] == 1
    assert d["fresh"] == ["a"]
    assert d["stale"] == [{"context_key": "b", "reason": "both"}]
    assert d["stale_fraction"] == 0.5
    assert report.stale[0].as_dict() == {"context_key": "b", "reason": "both"}

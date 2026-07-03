"""Tests for reviewer corrections per 100 extractions (§18.10 / §12.3)."""

from __future__ import annotations

from kg_eval.reviewer_corrections import (
    ReviewerCorrectionStats,
    corrections_per_100,
    count_decisions,
)


def _event(decision: str) -> dict[str, str]:
    return {"decision": decision}


def test_count_decisions_maps_each_decision_to_its_count() -> None:
    events = [
        _event("accepted"),
        _event("rejected"),
        _event("merged"),
        _event("split"),
        _event("corrected"),
    ]
    counts = count_decisions(events)
    assert counts == {
        "accepted": 1,
        "rejected": 1,
        "merged": 1,
        "split": 1,
        "corrected": 1,
    }


def test_unknown_decision_value_is_ignored() -> None:
    events = [_event("accepted"), _event("wontfix"), _event("rejected")]
    counts = count_decisions(events)
    assert "wontfix" not in counts
    assert counts["accepted"] == 1
    assert counts["rejected"] == 1
    # Recognised-but-unseen decisions stay at 0.
    assert counts["merged"] == 0


def test_corrections_per_100_over_100_extractions() -> None:
    events = [_event("rejected"), _event("rejected"), _event("corrected")]
    stats = corrections_per_100(events, total_extractions=100)
    # corrections = 2 rejected + 1 corrected = 3 → 100 * 3 / 100 = 3.0
    assert stats.corrections_per_100 == 3.0


def test_corrections_per_100_over_50_extractions() -> None:
    events = [_event("rejected"), _event("rejected"), _event("corrected")]
    stats = corrections_per_100(events, total_extractions=50)
    # 100 * 3 / 50 = 6.0
    assert stats.corrections_per_100 == 6.0


def test_total_extractions_zero_yields_zero_no_division_error() -> None:
    events = [_event("rejected"), _event("corrected")]
    stats = corrections_per_100(events, total_extractions=0)
    assert stats.corrections_per_100 == 0.0


def test_accepted_events_do_not_add_to_corrections() -> None:
    events = [_event("accepted"), _event("accepted"), _event("accepted")]
    stats = corrections_per_100(events, total_extractions=100)
    assert stats.accepted == 3
    assert stats.corrections_per_100 == 0.0


def test_as_dict_rounds_rate_and_keeps_int_fields() -> None:
    events = [_event("rejected"), _event("merged"), _event("split")]
    stats = corrections_per_100(events, total_extractions=30)
    d = stats.as_dict()
    # 100 * 3 / 30 = 10.0 (finite here, but confirm it is a rounded float).
    assert isinstance(d["corrections_per_100"], float)
    assert d["corrections_per_100"] == 10.0
    for field in ("total_extractions", "accepted", "rejected", "merged", "split", "corrected"):
        assert isinstance(d[field], int)


def test_as_dict_rounds_repeating_decimal() -> None:
    # 1 correction over 3 extractions = 33.333...; as_dict rounds to 4 places.
    events = [_event("rejected")]
    d = corrections_per_100(events, total_extractions=3).as_dict()
    assert d["corrections_per_100"] == 33.3333


def test_stats_is_frozen() -> None:
    stats = ReviewerCorrectionStats(
        total_extractions=1,
        accepted=0,
        rejected=1,
        merged=0,
        split=0,
        corrected=0,
        corrections_per_100=100.0,
    )
    try:
        stats.accepted = 5  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject mutation
        raise AssertionError("ReviewerCorrectionStats should be frozen")

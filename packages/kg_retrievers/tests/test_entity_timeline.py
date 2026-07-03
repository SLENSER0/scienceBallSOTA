"""Tests for the entity-detail timeline view-model (§17.11 / §5.2.4)."""

from __future__ import annotations

import json

from kg_retrievers.entity_timeline import (
    EVENT_KINDS,
    EntityTimeline,
    build_entity_timeline,
)


def test_event_kinds_frozenset() -> None:
    """EVENT_KINDS is exactly the three supported kinds as a frozenset."""
    assert set(EVENT_KINDS) == {"paper", "experiment", "curation"}
    assert isinstance(EVENT_KINDS, frozenset)


def test_empty_inputs_yield_empty_timeline() -> None:
    """No records -> empty events tuple and None span bounds."""
    timeline = build_entity_timeline([], [], [])
    assert timeline.events == ()
    assert timeline.span_start is None
    assert timeline.span_end is None


def test_mixed_events_ordered_by_date() -> None:
    """Paper 2019, curation 2020-03-01, experiment 2021-05 order chronologically."""
    papers = [{"ref_id": "p1", "year": 2019, "title": "Alpha"}]
    experiments = [{"ref_id": "e1", "date": "2021-05", "label": "Run"}]
    curation = [{"ref_id": "c1", "created_at": "2020-03-01", "label": "Merge"}]

    timeline = build_entity_timeline(papers, experiments, curation)

    kinds = [event["kind"] for event in timeline.events]
    assert kinds == ["paper", "curation", "experiment"]
    dates = [event["date"] for event in timeline.events]
    assert dates == ["2019-01-01", "2020-03-01", "2021-05"]
    assert timeline.span_start == "2019-01-01"
    assert timeline.span_end == "2021-05"


def test_ref_ids_preserved_unchanged() -> None:
    """Each event carries its source ref_id verbatim."""
    papers = [{"ref_id": "paper-42", "year": 2019}]
    experiments = [{"ref_id": "exp-7", "date": "2021-05"}]
    curation = [{"ref_id": "cur-9", "created_at": "2020-03-01"}]

    timeline = build_entity_timeline(papers, experiments, curation)

    ref_ids = {event["kind"]: event["ref_id"] for event in timeline.events}
    assert ref_ids == {"paper": "paper-42", "experiment": "exp-7", "curation": "cur-9"}


def test_bare_year_string_normalised() -> None:
    """A bare year string '2019' normalises the date field to '2019-01-01'."""
    timeline = build_entity_timeline([{"ref_id": "p1", "year": "2019"}], [], [])
    assert timeline.events[0]["date"] == "2019-01-01"
    assert timeline.span_start == "2019-01-01"


def test_same_date_tie_broken_by_kind_then_ref_id() -> None:
    """Same date -> kind order (paper<experiment<curation) then ref_id."""
    papers = [{"ref_id": "p1", "year": "2020"}]
    # Both experiments share the normalised paper date to force full tie-breaks.
    experiments = [
        {"ref_id": "e2", "date": "2020-01-01"},
        {"ref_id": "e1", "date": "2020-01-01"},
    ]
    curation = [{"ref_id": "c1", "created_at": "2020-01-01"}]

    timeline = build_entity_timeline(papers, experiments, curation)

    ordered = [(event["kind"], event["ref_id"]) for event in timeline.events]
    assert ordered == [
        ("paper", "p1"),
        ("experiment", "e1"),
        ("experiment", "e2"),
        ("curation", "c1"),
    ]


def test_as_dict_json_serialisable_and_counts_total() -> None:
    """as_dict() JSON-serialises; event count equals total input records."""
    papers = [{"ref_id": "p1", "year": 2019}, {"ref_id": "p2", "year": 2018}]
    experiments = [{"ref_id": "e1", "date": "2021-05"}]
    curation = [{"ref_id": "c1", "created_at": "2020-03-01"}]

    timeline = build_entity_timeline(papers, experiments, curation)
    data = timeline.as_dict()

    assert set(data) == {"events", "spanStart", "spanEnd"}
    assert len(data["events"]) == len(papers) + len(experiments) + len(curation)
    encoded = json.dumps(data)
    assert json.loads(encoded) == data


def test_timeline_is_frozen() -> None:
    """EntityTimeline is an immutable frozen dataclass."""
    timeline = build_entity_timeline([{"ref_id": "p1", "year": 2019}], [], [])
    assert isinstance(timeline, EntityTimeline)
    try:
        timeline.span_start = "x"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("EntityTimeline should be frozen")

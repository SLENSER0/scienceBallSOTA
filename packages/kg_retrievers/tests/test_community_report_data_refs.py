"""Tests for the inline community-report data-reference parser (§11.11)."""

from __future__ import annotations

from kg_retrievers.community_report_data_refs import (
    DataRefs,
    parse_data_refs,
    strip_data_refs,
)

_SAMPLE = (
    "Ti is strong [Data: Entities (12, 5); Relationships (3)]. "
    "See [Data: Reports (7)]. [Data: Entities (5)]"
)


def test_parse_merges_dedupes_and_sorts_by_type() -> None:
    refs = parse_data_refs(_SAMPLE)
    assert refs.by_type["Entities"] == (5, 12)
    assert refs.by_type["Relationships"] == (3,)
    assert refs.by_type["Reports"] == (7,)


def test_parse_counts_markers_and_total_refs() -> None:
    refs = parse_data_refs(_SAMPLE)
    # Three [Data: …] spans; unique ids across all types are {5, 12, 3, 7}.
    assert refs.n_markers == 3
    assert refs.total_refs == 4


def test_convenience_properties() -> None:
    refs = parse_data_refs(_SAMPLE)
    assert refs.entity_ids == (5, 12)
    assert refs.relationship_ids == (3,)
    assert refs.report_ids == (7,)


def test_case_insensitive_record_types() -> None:
    refs = parse_data_refs("x [data: entities (2, 1); REPORTS (9)]")
    assert refs.by_type["Entities"] == (1, 2)
    assert refs.by_type["Reports"] == (9,)
    assert refs.n_markers == 1
    assert refs.total_refs == 3


def test_no_markers_yields_empty_result() -> None:
    refs = parse_data_refs("no marks")
    assert refs.total_refs == 0
    assert refs.n_markers == 0
    assert refs.by_type == {}
    assert refs.entity_ids == ()
    assert refs.relationship_ids == ()
    assert refs.report_ids == ()


def test_strip_removes_span_and_collapses_double_space() -> None:
    assert strip_data_refs("a [Data: Entities (1)] b") == "a b"


def test_strip_multiple_spans() -> None:
    assert strip_data_refs(_SAMPLE) == "Ti is strong . See ."


def test_as_dict_is_json_friendly() -> None:
    refs = parse_data_refs("k [Data: Reports (3, 1)]")
    assert refs.as_dict() == {
        "by_type": {"Reports": [1, 3]},
        "n_markers": 1,
        "total_refs": 2,
    }


def test_dataclass_is_frozen() -> None:
    refs = DataRefs(by_type={}, n_markers=0, total_refs=0)
    try:
        refs.n_markers = 5  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject assignment
        raise AssertionError("DataRefs should be frozen")

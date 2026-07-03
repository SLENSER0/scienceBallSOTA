"""Tests for contradictions grouped by material / property (§15.4, §5.2.7)."""

from __future__ import annotations

from kg_retrievers.contradiction_cluster import (
    ContradictionGroup,
    cluster_contradictions,
    most_conflicted,
)


def _c(
    cid: str,
    material_id: str,
    property_id: str,
    relative_diff: float,
    subtype: str,
    measurement_ids: list[str],
) -> dict:
    return {
        "id": cid,
        "material_id": material_id,
        "property_id": property_id,
        "relative_diff": relative_diff,
        "contradiction_subtype": subtype,
        "measurement_ids": measurement_ids,
    }


def test_two_on_same_material_property_form_one_group() -> None:
    records = [
        _c("c1", "mat-A", "prop-band_gap", 0.31, "numeric_divergence", ["m1", "m2"]),
        _c("c2", "mat-A", "prop-band_gap", 0.72, "effect_direction", ["m2", "m3"]),
    ]
    groups = cluster_contradictions(records)

    assert len(groups) == 1
    group = groups[0]
    assert group.material_id == "mat-A"
    assert group.property_name == "prop-band_gap"
    # count == 2 for the two records on the same material+property.
    assert group.count == 2
    # max_relative_diff is the larger of the two (0.72, not 0.31).
    assert group.max_relative_diff == 0.72
    # subtypes deduped and sorted.
    assert group.subtypes == ("effect_direction", "numeric_divergence")
    # measurement_ids unioned across both records (m2 shared → once).
    assert group.measurement_ids == ("m1", "m2", "m3")
    # worst_id is the id of the higher-relative_diff record.
    assert group.worst_id == "c2"


def test_different_property_yields_separate_group() -> None:
    records = [
        _c("c1", "mat-A", "prop-band_gap", 0.40, "numeric_divergence", ["m1"]),
        _c("c2", "mat-A", "prop-band_gap", 0.55, "numeric_divergence", ["m2"]),
        _c("c3", "mat-A", "prop-conductivity", 0.90, "ci_disjoint", ["m9"]),
    ]
    groups = cluster_contradictions(records)

    # Two distinct (material, property) pairs → two groups.
    assert len(groups) == 2
    # Sorted by count desc: the 2-member band_gap group leads.
    assert groups[0].property_name == "prop-band_gap"
    assert groups[0].count == 2
    assert groups[1].property_name == "prop-conductivity"
    assert groups[1].count == 1
    assert groups[1].worst_id == "c3"
    assert groups[1].max_relative_diff == 0.90


def test_sort_by_count_then_max_relative_diff() -> None:
    # Two single-member groups; the one with the larger divergence ranks first.
    records = [
        _c("c1", "mat-A", "prop-x", 0.35, "numeric_divergence", ["m1"]),
        _c("c2", "mat-B", "prop-y", 0.80, "numeric_divergence", ["m2"]),
    ]
    groups = cluster_contradictions(records)
    assert [g.material_id for g in groups] == ["mat-B", "mat-A"]


def test_property_name_fallback_when_no_property_id() -> None:
    records = [
        {
            "id": "c1",
            "material_id": "mat-Z",
            "property_name": "melting_point",
            "relative_diff": 0.5,
            "contradiction_subtype": "numeric_divergence",
            "measurement_ids": ["m1"],
        }
    ]
    groups = cluster_contradictions(records)
    assert len(groups) == 1
    assert groups[0].property_name == "melting_point"


def test_worst_id_tracks_highest_relative_diff() -> None:
    records = [
        _c("low", "mat-A", "prop-x", 0.31, "numeric_divergence", ["m1"]),
        _c("high", "mat-A", "prop-x", 0.99, "numeric_divergence", ["m2"]),
        _c("mid", "mat-A", "prop-x", 0.60, "numeric_divergence", ["m3"]),
    ]
    groups = cluster_contradictions(records)
    assert len(groups) == 1
    assert groups[0].worst_id == "high"
    assert groups[0].max_relative_diff == 0.99


def test_most_conflicted_returns_highest_count_group() -> None:
    records = [
        _c("c1", "mat-A", "prop-x", 0.40, "numeric_divergence", ["m1"]),
        _c("c2", "mat-A", "prop-x", 0.50, "effect_direction", ["m2"]),
        _c("c3", "mat-B", "prop-y", 0.95, "ci_disjoint", ["m9"]),
    ]
    groups = cluster_contradictions(records)
    top = most_conflicted(groups)
    assert top is not None
    assert top.material_id == "mat-A"
    assert top.property_name == "prop-x"
    assert top.count == 2


def test_most_conflicted_none_for_empty() -> None:
    assert most_conflicted([]) is None
    assert cluster_contradictions([]) == []


def test_as_dict_round_trip() -> None:
    group = ContradictionGroup(
        material_id="mat-A",
        property_name="prop-x",
        count=2,
        max_relative_diff=0.72,
        subtypes=("effect_direction", "numeric_divergence"),
        measurement_ids=("m1", "m2"),
        worst_id="c2",
    )
    assert group.as_dict() == {
        "material_id": "mat-A",
        "property_name": "prop-x",
        "count": 2,
        "max_relative_diff": 0.72,
        "subtypes": ["effect_direction", "numeric_divergence"],
        "measurement_ids": ["m1", "m2"],
        "worst_id": "c2",
    }

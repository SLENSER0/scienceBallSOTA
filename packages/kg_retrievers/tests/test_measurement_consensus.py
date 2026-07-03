"""Tests for measurement consensus / value reconciliation (§15.4).

Проверяем сведение группы противоречивых измерений к единой оценке: взвешенное
среднее, относительный разброс, выбор якоря и выявление выбросов.
"""

from __future__ import annotations

from kg_retrievers.measurement_consensus import ConsensusEstimate, consensus_estimate


def _m(mid: str, value: float, conf: float, unit: str = "MPa") -> dict:
    """Build one normalized Measurement dict."""
    return {
        "id": mid,
        "value_normalized": value,
        "normalized_unit": unit,
        "confidence": conf,
        "evidence_strength": "peer_reviewed",
    }


def test_two_identical_values_no_spread_no_outliers() -> None:
    result = consensus_estimate([_m("a", 200.0, 0.8), _m("b", 200.0, 0.8)])
    assert result is not None
    assert result.estimate == 200.0
    assert result.relative_spread == 0.0
    assert result.outlier_ids == ()
    assert result.member_count == 2
    assert result.weighted is True


def test_weighted_mean_pulls_toward_high_confidence_member() -> None:
    result = consensus_estimate([_m("a", 100.0, 0.9), _m("b", 140.0, 0.1)])
    assert result is not None
    # Plain mean is 120.0; weighting must pull the estimate toward 100.
    assert result.estimate < 120.0
    assert abs(result.estimate - 104.0) < 1e-9  # (100*0.9 + 140*0.1) / 1.0


def test_lone_member_below_min_returns_none() -> None:
    assert consensus_estimate([_m("a", 100.0, 0.9)], min_members=2) is None


def test_mismatched_units_return_none() -> None:
    members = [_m("a", 100.0, 0.9, unit="MPa"), _m("b", 100.0, 0.9, unit="GPa")]
    assert consensus_estimate(members) is None


def test_outlier_flagged_among_tight_cluster() -> None:
    members = [
        _m("a", 100.0, 0.5),
        _m("b", 110.0, 0.5),
        _m("c", 105.0, 0.5),
        _m("d", 500.0, 0.5),
    ]
    result = consensus_estimate(members, outlier_tol=0.5)
    assert result is not None
    # estimate = (100+110+105+500)/4 = 203.75 (equal weights -> plain mean).
    # d=500 deviates by 1.454 of the estimate; the tight cluster stays inside
    # tolerance except a, which the extreme 500 drags marginally past 0.5.
    assert "d" in result.outlier_ids  # |500-203.75|/203.75 = 1.454 > 0.5
    assert "b" not in result.outlier_ids  # |110-203.75|/203.75 = 0.460 < 0.5
    assert "c" not in result.outlier_ids  # |105-203.75|/203.75 = 0.485 < 0.5


def test_anchor_is_highest_confidence_member() -> None:
    members = [_m("a", 100.0, 0.2), _m("b", 140.0, 0.95), _m("c", 120.0, 0.4)]
    result = consensus_estimate(members)
    assert result is not None
    assert result.anchor_measurement_id == "b"


def test_as_dict_round_trips_all_nine_keys() -> None:
    result = consensus_estimate(
        [_m("a", 100.0, 0.5), _m("b", 110.0, 0.5)],
        subject_key="steel/yield",
        property_name="yield_strength",
    )
    assert result is not None
    data = result.as_dict()
    expected_keys = {
        "subject_key",
        "property_name",
        "unit",
        "estimate",
        "weighted",
        "member_count",
        "relative_spread",
        "anchor_measurement_id",
        "outlier_ids",
    }
    assert set(data.keys()) == expected_keys
    assert len(expected_keys) == 9
    assert data["subject_key"] == "steel/yield"
    assert data["property_name"] == "yield_strength"
    assert data["unit"] == "MPa"
    assert data["outlier_ids"] == list(result.outlier_ids)
    # Reconstruct the dataclass from the mapping to confirm a clean round-trip.
    rebuilt = ConsensusEstimate(
        subject_key=data["subject_key"],
        property_name=data["property_name"],
        unit=data["unit"],
        estimate=data["estimate"],
        weighted=data["weighted"],
        member_count=data["member_count"],
        relative_spread=data["relative_spread"],
        anchor_measurement_id=data["anchor_measurement_id"],
        outlier_ids=tuple(data["outlier_ids"]),
    )
    assert rebuilt == result


def test_zero_confidence_falls_back_to_plain_mean() -> None:
    members = [_m("a", 100.0, 0.0), _m("b", 200.0, 0.0)]
    result = consensus_estimate(members)
    assert result is not None
    assert result.weighted is False
    assert result.estimate == 150.0

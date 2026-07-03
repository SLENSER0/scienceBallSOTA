"""Tests for expected extractor-missed-fact backlog (§25.11).

RU: проверяет missed_prob и агрегацию estimate_missed_facts.
EN: checks missed_prob and estimate_missed_facts aggregation.
"""

from __future__ import annotations

from kg_retrievers.expected_missed_facts import (
    MissedFactEstimate,
    estimate_missed_facts,
    missed_prob,
)


def _cell(material_id: str, property_name: str, status: str, conf: object) -> dict:
    return {
        "material_id": material_id,
        "property_name": property_name,
        "status": status,
        "confidence_of_absence": conf,
    }


def test_possible_absence_missed_prob() -> None:
    # (1) POSSIBLE_ABSENCE with confidence_of_absence=0.6 → 0.4.
    cell = _cell("M1", "band_gap", "POSSIBLE_ABSENCE", 0.6)
    assert abs(missed_prob(cell) - 0.4) < 1e-9


def test_covered_cell_zero() -> None:
    # (2) COVERED cell → 0.0.
    cell = _cell("M1", "band_gap", "COVERED", 0.6)
    assert missed_prob(cell) == 0.0


def test_unknown_confidence_zero() -> None:
    # (3) confidence_of_absence == 'unknown' → 0.0.
    cell = _cell("M1", "band_gap", "POSSIBLE_ABSENCE", "unknown")
    assert missed_prob(cell) == 0.0


def test_total_sums_within_tolerance() -> None:
    # (4) cells 0.4 and 0.3 → total 0.7 within 1e-9.
    cells = [
        _cell("M1", "band_gap", "POSSIBLE_ABSENCE", 0.6),  # 0.4
        _cell("M2", "hardness", "LIKELY_ABSENCE", 0.7),  # 0.3
    ]
    est = estimate_missed_facts(cells)
    assert abs(est.total_expected - 0.7) < 1e-9


def test_by_property_groups_independently() -> None:
    # (5) two distinct properties bucketed separately.
    cells = [
        _cell("M1", "band_gap", "POSSIBLE_ABSENCE", 0.6),  # 0.4
        _cell("M2", "hardness", "LIKELY_ABSENCE", 0.7),  # 0.3
    ]
    est = estimate_missed_facts(cells)
    assert set(est.by_property) == {"band_gap", "hardness"}
    assert abs(est.by_property["band_gap"] - 0.4) < 1e-9
    assert abs(est.by_property["hardness"] - 0.3) < 1e-9


def test_by_property_same_property_accumulates() -> None:
    cells = [
        _cell("M1", "band_gap", "POSSIBLE_ABSENCE", 0.6),  # 0.4
        _cell("M2", "band_gap", "LIKELY_ABSENCE", 0.7),  # 0.3
    ]
    est = estimate_missed_facts(cells)
    assert set(est.by_property) == {"band_gap"}
    assert abs(est.by_property["band_gap"] - 0.7) < 1e-9


def test_ranked_highest_first() -> None:
    # (6) ranked[0] is the highest missed_prob.
    cells = [
        _cell("M2", "hardness", "LIKELY_ABSENCE", 0.7),  # 0.3
        _cell("M1", "band_gap", "POSSIBLE_ABSENCE", 0.6),  # 0.4
        _cell("M3", "density", "POSSIBLE_ABSENCE", 0.9),  # 0.1
    ]
    est = estimate_missed_facts(cells)
    assert est.ranked[0] == ("M1", "band_gap", 0.4)
    probs = [row[2] for row in est.ranked]
    assert probs == sorted(probs, reverse=True)


def test_empty_input() -> None:
    # (7) empty input → total_expected 0.0 and ranked [].
    est = estimate_missed_facts([])
    assert est.total_expected == 0.0
    assert est.ranked == []
    assert est.by_material == {}
    assert est.by_property == {}


def test_as_dict_roundtrip() -> None:
    est = estimate_missed_facts([_cell("M1", "band_gap", "POSSIBLE_ABSENCE", 0.6)])
    d = est.as_dict()
    assert abs(d["total_expected"] - 0.4) < 1e-9
    assert d["ranked"] == [["M1", "band_gap", 0.4]]
    assert d["by_material"] == {"M1": 0.4}


def test_frozen_dataclass() -> None:
    est = MissedFactEstimate(0.0, {}, {}, [])
    try:
        est.total_expected = 1.0  # type: ignore[misc]
    except (AttributeError, TypeError):
        return
    raise AssertionError("MissedFactEstimate should be frozen")


def test_bool_confidence_rejected() -> None:
    # bool is not a usable numeric confidence.
    cell = _cell("M1", "band_gap", "POSSIBLE_ABSENCE", True)
    assert missed_prob(cell) == 0.0

"""Tests for absence value-of-information ranking (§25.11).

RU: Тесты ранжирования ячеек отсутствия по value of information.
EN: Tests for value-of-information ranking of absence cells.
"""

from __future__ import annotations

import pytest

from kg_retrievers.absence_value_of_information import (
    VoICell,
    VoIReport,
    _binary_entropy,
    rank_value_of_information,
)


def test_binary_entropy_peak_at_half() -> None:
    """RU: H(0.5)=1. EN: fair coin has one bit of entropy."""
    assert _binary_entropy(0.5) == 1.0


def test_binary_entropy_certain_ends_are_zero() -> None:
    """RU: H(0)=H(1)=0. EN: certain outcomes carry no entropy."""
    assert _binary_entropy(0.0) == 0.0
    assert _binary_entropy(1.0) == 0.0


def test_binary_entropy_quarter() -> None:
    """RU: H(0.25) — известное значение. EN: hand-checked H(0.25)."""
    assert _binary_entropy(0.25) == pytest.approx(0.8112781, abs=1e-6)


def test_ambiguous_cell_outranks_confident_one() -> None:
    """RU: p=0.5 важнее p=0.9. EN: p=0.5 outranks p=0.9 by VoI."""
    cells = [
        {"material_id": "m2", "property_name": "band_gap", "p_extractor_missed": 0.9},
        {"material_id": "m1", "property_name": "band_gap", "p_extractor_missed": 0.5},
    ]
    report = rank_value_of_information(cells)
    assert report.cells[0].material_id == "m1"
    assert report.cells[0].voi > report.cells[1].voi


def test_total_voi_is_sum_of_cell_voi() -> None:
    """RU: total_voi = сумма voi ячеек. EN: total_voi equals sum of cell VoI."""
    cells = [
        {"material_id": "m1", "property_name": "a", "p_extractor_missed": 0.5},
        {"material_id": "m2", "property_name": "b", "p_extractor_missed": 0.25},
        {"material_id": "m3", "property_name": "c", "p_extractor_missed": 0.75},
    ]
    report = rank_value_of_information(cells)
    assert report.total_voi == pytest.approx(sum(c.voi for c in report.cells))


def test_top_n_truncates_top_not_cells() -> None:
    """RU: top_n усекает top, не cells. EN: top_n truncates top, keeps all cells."""
    cells = [
        {"material_id": "m1", "property_name": "a", "p_extractor_missed": 0.5},
        {"material_id": "m2", "property_name": "b", "p_extractor_missed": 0.25},
        {"material_id": "m3", "property_name": "c", "p_extractor_missed": 0.75},
    ]
    report = rank_value_of_information(cells, top_n=1)
    assert len(report.top) == 1
    assert len(report.cells) == 3
    # Top cell is the most ambiguous (p=0.5).
    assert report.top[0].material_id == "m1"


def test_missing_p_key_yields_zero_voi() -> None:
    """RU: без p_extractor_missed → voi=0. EN: missing p_key gives voi 0.0."""
    cells = [
        {"material_id": "m1", "property_name": "a"},
        {"material_id": "m2", "property_name": "b", "p_extractor_missed": 0.5},
    ]
    report = rank_value_of_information(cells)
    by_id = {c.material_id: c for c in report.cells}
    assert by_id["m1"].voi == 0.0
    # The scored cell sorts ahead of the zero-VoI cell.
    assert report.cells[0].material_id == "m2"


def test_as_dict_round_trips_top_as_list() -> None:
    """RU: as_dict сериализует top как список. EN: as_dict emits top as a list."""
    cells = [
        {"material_id": "m1", "property_name": "a", "p_extractor_missed": 0.5},
        {"material_id": "m2", "property_name": "b", "p_extractor_missed": 0.9},
    ]
    report = rank_value_of_information(cells, top_n=1)
    data = report.as_dict()
    assert isinstance(data["top"], list)
    assert data["top"] == [report.top[0].as_dict()]
    assert data["top"][0]["material_id"] == "m1"


def test_dataclasses_are_frozen() -> None:
    """RU: dataclass'ы заморожены. EN: dataclasses are frozen."""
    cell = VoICell(material_id="m", property_name="p", p_missed=0.5, voi=1.0)
    report = VoIReport(cells=(cell,), total_voi=1.0, top=(cell,))
    with pytest.raises((AttributeError, TypeError)):
        cell.voi = 0.0  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        report.total_voi = 0.0  # type: ignore[misc]

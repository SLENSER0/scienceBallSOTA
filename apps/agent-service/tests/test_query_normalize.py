"""Tests for §13.7 query unit-normalization (:mod:`agent_service.query_normalize`).

Deterministic, hand-checkable: каждый ассерт сверяется с числом, посчитанным
вручную (K→°C: 1073-273.15=799.85; min→h: 30/60=0.5; бар→МПа: 5/10=0.5), а не
с выводом самой функции.
"""

from __future__ import annotations

import pytest
from agent_service.query_normalize import NormalizedQuery, normalize_query


def test_temperature_c_and_time() -> None:
    # «закалка при 500 °C, 2 ч» → temperature_c=500, time_h=2.
    nq = normalize_query("закалка при 500 °C, 2 ч")
    assert nq.numeric_constraints["temperature_c"] == 500.0
    assert nq.numeric_constraints["time_h"] == 2.0
    assert nq.units_found == ["°C", "h"]
    assert "2 h" in nq.normalized_text  # ч → h переписан


def test_kelvin_to_celsius() -> None:
    # 1073 K − 273.15 = 799.85 ≈ 800 °C.
    nq = normalize_query("аустенитизация 1073 K")
    assert nq.numeric_constraints["temperature_c"] == pytest.approx(800.0, abs=1.0)
    assert nq.numeric_constraints["temperature_c"] == pytest.approx(799.85)
    assert nq.units_found == ["K"]


def test_minutes_to_hours() -> None:
    # 30 min = 30/60 = 0.5 h.
    nq = normalize_query("выдержка 30 min")
    assert nq.numeric_constraints["time_h"] == 0.5
    assert nq.units_found == ["min"]
    assert "30 min" in nq.normalized_text


def test_seconds_to_hours() -> None:
    # 10 с = 10/3600 ≈ 0.002778 h; «с» переписывается в канон «s».
    nq = normalize_query("выдержка 10 с")
    assert nq.numeric_constraints["time_h"] == pytest.approx(10 / 3600, abs=1e-6)
    assert nq.units_found == ["s"]
    assert "10 s" in nq.normalized_text


def test_pressure_mpa_captured() -> None:
    # 250 MPa захвачено в pressure_mpa (MPa → 2500 бар → /10 = 250).
    nq = normalize_query("давление 250 MPa")
    assert nq.numeric_constraints["pressure_mpa"] == 250.0
    assert nq.units_found == ["MPa"]


def test_pressure_bar_to_mpa() -> None:
    # 5 бар = 5/10 = 0.5 МПа.
    nq = normalize_query("давление 5 бар")
    assert nq.numeric_constraints["pressure_mpa"] == 0.5
    assert nq.units_found == ["bar"]


def test_composition_wt_pct_captured() -> None:
    # «0.3 wt%» захвачено как composition_wt_pct.
    nq = normalize_query("содержание углерода 0.3 wt%")
    assert nq.numeric_constraints["composition_wt_pct"] == 0.3
    assert "wt%" in nq.units_found


def test_composition_at_pct() -> None:
    # «2 at%» захвачено как composition_at_pct (атомные проценты).
    nq = normalize_query("2 at% Cr")
    assert nq.numeric_constraints["composition_at_pct"] == 2.0
    assert nq.units_found == ["at%"]


def test_hardness_scales_separate_keys() -> None:
    # HV/HRC/HB — несопоставимые шкалы, каждая под своим ключом.
    nq = normalize_query("твёрдость 45 HRC и 200 HV, основа 180 HB")
    assert nq.numeric_constraints["hardness_hrc"] == 45.0
    assert nq.numeric_constraints["hardness_hv"] == 200.0
    assert nq.numeric_constraints["hardness_hb"] == 180.0


def test_multiple_constraints() -> None:
    # Несколько условий разных семейств в одном запросе.
    nq = normalize_query("отпуск 200 °C, 1 ч, твёрдость 45 HRC")
    assert nq.numeric_constraints == {
        "temperature_c": 200.0,
        "time_h": 1.0,
        "hardness_hrc": 45.0,
    }


def test_no_number_empty_constraints() -> None:
    # Текст без чисел → пустые условия и единицы, текст не изменён.
    nq = normalize_query("механические свойства легированной стали")
    assert nq.numeric_constraints == {}
    assert nq.units_found == []
    assert nq.normalized_text == "механические свойства легированной стали"


def test_rewrite_cyrillic_units_to_canonical() -> None:
    # Кириллические написания единиц → канон: °с→°C, ч→h, мпа→MPa.
    nq = normalize_query("500 °с, 2 ч, 200 мпа")
    assert nq.normalized_text == "500 °C, 2 h, 200 MPa"
    assert nq.numeric_constraints == {
        "temperature_c": 500.0,
        "time_h": 2.0,
        "pressure_mpa": 200.0,
    }


def test_as_dict_shape() -> None:
    # as_dict() отдаёт ровно три поля с копиями коллекций.
    nq = normalize_query("закалка 850 °C, 30 min")
    d = nq.as_dict()
    assert set(d) == {"normalized_text", "numeric_constraints", "units_found"}
    assert d["numeric_constraints"] == {"temperature_c": 850.0, "time_h": 0.5}
    assert d["units_found"] == ["°C", "min"]
    assert isinstance(d["numeric_constraints"], dict)
    assert isinstance(d["units_found"], list)


def test_frozen_dataclass() -> None:
    # NormalizedQuery неизменяем (frozen).
    nq = normalize_query("1 ч")
    assert isinstance(nq, NormalizedQuery)
    with pytest.raises(Exception):  # noqa: B017 — FrozenInstanceError
        nq.normalized_text = "x"  # type: ignore[misc]

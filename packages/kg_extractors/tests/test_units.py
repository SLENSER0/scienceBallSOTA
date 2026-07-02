"""Unit normalization + numeric-constraint parsing (§7 / §24.4)."""

from __future__ import annotations

import pytest

from kg_extractors.units import parse_numeric_constraints, to_canonical


def test_mg_per_dm3_equals_mg_per_l() -> None:
    a = to_canonical(300, "мг/дм³")
    b = to_canonical(300, "мг/л")
    assert a is not None and b is not None
    assert a.unit == "mg/L" and abs(a.value - 300) < 1e-6
    assert abs(a.value - b.value) < 1e-6


def test_g_per_l_to_mg_per_l() -> None:
    n = to_canonical(1, "г/л")
    assert n is not None and n.unit == "mg/L"
    assert abs(n.value - 1000) < 1e-6


def test_current_density_and_temp() -> None:
    cd = to_canonical(250, "А/м²")
    assert cd is not None and cd.unit == "A/m^2" and abs(cd.value - 250) < 1e-6
    t = to_canonical(60, "°C")
    assert t is not None and abs(t.value - 60) < 1e-6


def test_parse_le_constraint() -> None:
    cs = parse_numeric_constraints("требуемый сухой остаток ≤1000 мг/дм³")
    assert cs
    c = cs[0]
    assert c.operator == "<=" and c.value == 1000
    assert c.normalized_unit == "mg/L" and abs(c.normalized_value - 1000) < 1e-6


def test_parse_range() -> None:
    cs = parse_numeric_constraints("сульфаты, хлориды по 200–300 мг/л")
    rng = [c for c in cs if c.operator == "range"]
    assert rng and rng[0].min == 200 and rng[0].max == 300
    assert rng[0].normalized_unit == "mg/L"


def test_parse_velocity_range() -> None:
    cs = parse_numeric_constraints("скорость потока 0.1–0.3 м/с")
    rng = [c for c in cs if c.operator == "range"]
    assert rng and abs(rng[0].min - 0.1) < 1e-9 and abs(rng[0].max - 0.3) < 1e-9
    assert rng[0].normalized_unit == "m/s"


@pytest.mark.parametrize("text", ["сульфаты <200 мг/л", "sulfates <200 mg/L"])
def test_ru_en_parity(text: str) -> None:
    cs = parse_numeric_constraints(text)
    lt = [c for c in cs if c.operator == "<"]
    assert lt and lt[0].value == 200 and lt[0].normalized_unit == "mg/L"


# --- adversarial-review regression tests ---


def test_single_letter_units_not_fabricated() -> None:
    # "5 кг" and "30 минут" must NOT yield "5 к" / "30 м" measurements (finding units:230)
    cs = parse_numeric_constraints("добавили 5 кг купороса и перемешивали 30 минут")
    assert all(c.unit not in {"к", "м", "v"} for c in cs)


def test_year_range_not_parsed_as_measurement() -> None:
    # "2015-2020" (no unit) must not become a numeric range (finding units:278)
    cs = parse_numeric_constraints("методы за 2015-2020 годы и в 2019–2021")
    assert not [c for c in cs if c.operator == "range"]


def test_voltage_normalizes() -> None:
    # volt dimensionality fixed (finding units:177): 0.5 V == 500 mV
    v = to_canonical(0.5, "в")
    mv = to_canonical(500, "мв")
    assert v is not None and mv is not None
    assert v.unit == "V" and mv.unit == "V"
    assert abs(v.value - mv.value) < 1e-6


def test_ppm_magnitude_preserved() -> None:
    # ppm must not collapse to a tiny percent (finding units:189)
    n = to_canonical(100, "ppm")
    assert n is not None and n.unit == "ppm" and abs(n.value - 100) < 1e-6

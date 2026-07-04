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


@pytest.mark.parametrize("sep", [" ", "\u00A0", "\u202F"])  # space / NBSP / narrow-NBSP
def test_thousands_separator_in_constraint(sep: str) -> None:
    # "1 000" (regular / NBSP / narrow-NBSP) must parse as 1000, not 1 + a bogus
    # second "000" constraint, and not as 0.
    text = f"сухой остаток ≤1{sep}000 мг/дм³"
    cs = parse_numeric_constraints(text)
    le = [c for c in cs if c.operator == "<="]
    assert le and le[0].value == 1000
    assert le[0].normalized_unit == "mg/L" and abs(le[0].normalized_value - 1000) < 1e-6
    # no fabricated zero-valued companion constraint
    assert all(c.value != 0 for c in cs if c.value is not None)


def test_thousands_separator_million() -> None:
    # "1 000 000 мг/л" -> single 1e6 magnitude, not truncated to 1 or 0.
    cs = parse_numeric_constraints("предел 1 000 000 мг/л")
    vals = [c.value for c in cs if c.unit and c.value is not None]
    assert 1_000_000 in vals


# --- M-31: kg/m^3 is a density, not a mg/L concentration ---


def test_kg_per_m3_is_density_not_concentration() -> None:
    n = to_canonical(1200, "кг/м3")
    assert n is not None
    # value preserved (NOT rescaled ×1000 into 1.2e6 mg/L)
    assert abs(n.value - 1200) < 1e-6
    assert n.unit != "mg/L"


def test_concentration_still_normalizes_after_density_fix() -> None:
    # guard: real mass concentrations must still convert to mg/L
    assert to_canonical(1, "г/л").unit == "mg/L"
    assert abs(to_canonical(1, "г/л").value - 1000) < 1e-6


# --- M-20: bare years / counters must not become measurements ---


@pytest.mark.parametrize(
    "text", ["данные после 2015", "методы от 2015 года", "более 2015 образцов", "до 2020"]
)
def test_year_like_not_parsed_as_constraint(text: str) -> None:
    cs = parse_numeric_constraints(text)
    assert not [c for c in cs if c.value in (2015.0, 2020.0)]


def test_unitless_prose_number_not_fabricated() -> None:
    # unit-less directional prose ("менее 500 проб") is not a measurement
    cs = parse_numeric_constraints("менее 500 проб отобрано")
    assert not [c for c in cs if c.unit is None]


def test_unitless_symbolic_comparison_preserved() -> None:
    # explicit comparison symbol with a non-year value is still a real constraint
    cs = parse_numeric_constraints("pH < 7 в растворе")
    lt = [c for c in cs if c.operator == "<"]
    assert lt and lt[0].value == 7

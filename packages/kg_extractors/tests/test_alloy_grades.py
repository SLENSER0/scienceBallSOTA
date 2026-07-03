"""Standard alloy-grade + composition-fraction parsing tests (§6.4)."""

from __future__ import annotations

from kg_extractors.alloy_grades import (
    ElementFraction,
    GradeMatch,
    parse_composition_fractions,
    parse_grade,
)

# ---------------------------------------------------------------------------
# parse_grade
# ---------------------------------------------------------------------------


def test_grade_aa2024_system_and_dict() -> None:
    gm = parse_grade("Сплав AA2024 после закалки.")
    assert gm == GradeMatch(grade="2024", system="AA", temper=None, source_span="AA2024")
    assert gm.as_dict() == {
        "grade": "2024",
        "system": "AA",
        "temper": None,
        "source_span": "AA2024",
    }


def test_grade_2024_t6_temper() -> None:
    gm = parse_grade("Образец 2024-T6 испытан на растяжение.")
    assert gm is not None
    assert gm.grade == "2024"
    assert gm.system == "AA"
    assert gm.temper == "T6"
    assert gm.source_span == "2024-T6"


def test_grade_6061_t651_temper() -> None:
    gm = parse_grade("Plate of 6061-T651 was machined.")
    assert gm == GradeMatch(grade="6061", system="AA", temper="T651", source_span="6061-T651")


def test_grade_inconel_718() -> None:
    gm = parse_grade("The turbine disk used Inconel 718.")
    assert gm is not None
    assert gm.grade == "718"
    assert gm.system == "Inconel"
    assert gm.temper is None
    assert gm.source_span == "Inconel 718"


def test_grade_ti_6al_4v() -> None:
    gm = parse_grade("Титановый сплав Ti-6Al-4V широко применяется.")
    assert gm is not None
    assert gm.grade == "Ti-6Al-4V"
    assert gm.system == "Ti"
    assert gm.temper is None
    assert gm.source_span == "Ti-6Al-4V"


def test_grade_316l_stainless() -> None:
    gm = parse_grade("Corrosion tests on 316L coupons.")
    assert gm == GradeMatch(grade="316L", system="AISI", temper=None, source_span="316L")


def test_grade_none_when_absent() -> None:
    assert parse_grade("A polished specimen was examined under the microscope.") is None
    assert parse_grade("Металлический образец без марки был очищен.") is None
    assert parse_grade("") is None


# ---------------------------------------------------------------------------
# parse_composition_fractions
# ---------------------------------------------------------------------------


def test_fraction_weight_percent() -> None:
    res = parse_composition_fractions("Добавили 4.5 wt% Cu в расплав.")
    assert res == [ElementFraction(element="Cu", value=4.5, fraction_type="wt", is_balance=False)]


def test_fraction_atomic_percent() -> None:
    res = parse_composition_fractions("Содержание 2 at.% Mg зафиксировано.")
    assert res == [ElementFraction(element="Mg", value=2.0, fraction_type="at", is_balance=False)]


def test_fraction_russian_mass_percent() -> None:
    res = parse_composition_fractions("Легирование 4.5 масс.% Cu.")
    assert res == [ElementFraction(element="Cu", value=4.5, fraction_type="wt", is_balance=False)]


def test_fraction_balance_is_balance_true() -> None:
    res = parse_composition_fractions("Al balance")
    assert res == [
        ElementFraction(element="Al", value=None, fraction_type="unknown", is_balance=True)
    ]
    assert res[0].as_dict() == {
        "element": "Al",
        "value": None,
        "fraction_type": "unknown",
        "is_balance": True,
    }


def test_fraction_bare_percent_unknown_type() -> None:
    res = parse_composition_fractions("Примесь Zn 3.2% обнаружена.")
    assert res == [
        ElementFraction(element="Zn", value=3.2, fraction_type="unknown", is_balance=False)
    ]


def test_fraction_russian_at_and_balance_ordered() -> None:
    res = parse_composition_fractions("Состав: 2 ат.% Mg, Al ост.")
    assert res == [
        ElementFraction(element="Mg", value=2.0, fraction_type="at", is_balance=False),
        ElementFraction(element="Al", value=None, fraction_type="unknown", is_balance=True),
    ]


def test_fraction_empty_and_no_element() -> None:
    assert parse_composition_fractions("") == []
    # A bare percent with no adjacent element is not an element fraction.
    assert parse_composition_fractions("Yield rose by 5% overall.") == []

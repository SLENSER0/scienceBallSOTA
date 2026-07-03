"""GOST Cyrillic alloy/steel grade parsing tests (§6.4, §24)."""

from __future__ import annotations

from kg_extractors.gost_grades import (
    GostGrade,
    cyrillic_element_map,
    parse_gost_grade,
)

# ---------------------------------------------------------------------------
# cyrillic_element_map
# ---------------------------------------------------------------------------


def test_cyrillic_map_translations() -> None:
    m = cyrillic_element_map()
    assert m["Х"] == "Cr"
    assert m["Н"] == "Ni"
    assert m["Г"] == "Mn"
    assert m["С"] == "Si"
    assert m["Т"] == "Ti"
    assert m["М"] == "Mo"
    assert m["Ф"] == "V"
    assert m["Д"] == "Cu"


def test_cyrillic_map_returns_fresh_copy() -> None:
    m = cyrillic_element_map()
    m["Х"] = "MUTATED"
    assert cyrillic_element_map()["Х"] == "Cr"  # module table is not shared


# ---------------------------------------------------------------------------
# parse_gost_grade — structural alloy steels
# ---------------------------------------------------------------------------


def test_stainless_12kh18n10t() -> None:
    g = parse_gost_grade("12Х18Н10Т")
    assert g is not None
    assert g.grade_type == "steel"
    assert g.carbon_pct == 0.12
    assert g.elements["Cr"] == 18.0
    assert g.elements["Ni"] == 10.0
    assert "Ti" in g.elements  # bare Т carries no percent digit
    assert g.elements["Ti"] is None


def test_40kh_carbon_and_chromium() -> None:
    g = parse_gost_grade("40Х")
    assert g is not None
    assert g.carbon_pct == 0.40
    assert "Cr" in g.elements
    assert g.elements["Cr"] is None  # bare Х: chromium present, percent unspecified


def test_multiletter_alloy_percents() -> None:
    g = parse_gost_grade("30ХГСА")
    assert g is not None
    assert g.grade_type == "steel"
    assert g.carbon_pct == 0.30
    assert g.elements["Cr"] is None
    assert g.elements["Mn"] is None
    assert g.elements["Si"] is None  # trailing А (nitrogen/quality) is not an element


# ---------------------------------------------------------------------------
# parse_gost_grade — plain carbon steel & aluminum
# ---------------------------------------------------------------------------


def test_plain_carbon_steel_st3() -> None:
    g = parse_gost_grade("Ст3")
    assert g is not None
    assert g.grade_type == "steel"
    assert g.carbon_pct is None
    assert g.elements == {}


def test_aluminum_d16() -> None:
    g = parse_gost_grade("Д16")
    assert g is not None
    assert g.grade_type == "aluminum"
    assert g.carbon_pct is None


def test_aluminum_amg6() -> None:
    g = parse_gost_grade("АМг6")
    assert g is not None
    assert g.grade_type == "aluminum"


# ---------------------------------------------------------------------------
# parse_gost_grade — negatives, embedding, round-trip
# ---------------------------------------------------------------------------


def test_no_grade_in_latin_prose() -> None:
    assert parse_gost_grade("hello world") is None
    assert parse_gost_grade("") is None
    assert parse_gost_grade("Металлический образец без марки") is None  # no digit


def test_leftmost_grade_extracted_from_sentence() -> None:
    g = parse_gost_grade("Образец 40Х испытан на растяжение.")
    assert g is not None
    assert g.carbon_pct == 0.40
    assert "Cr" in g.elements


def test_as_dict_round_trips_all_fields() -> None:
    g = parse_gost_grade("12Х18Н10Т")
    assert g is not None
    d = g.as_dict()
    assert d == {
        "raw": g.raw,
        "grade_type": "steel",
        "normalized": g.normalized,
        "carbon_pct": 0.12,
        "elements": {"Cr": 18.0, "Ni": 10.0, "Ti": None},
    }
    assert GostGrade(**d) == g  # every field survives the round trip

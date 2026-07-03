"""Composition extraction from prose (§6.4)."""

from __future__ import annotations

from kg_extractors.composition_extractor import extract_compositions


def test_dash_notation_alloy() -> None:
    text = "Исследовали сплав Al-4Cu-1Mg после старения."
    comps = [c for c in extract_compositions(text) if c.kind == "dash"]
    assert comps
    c = comps[0]
    assert c.base_element == "Al"
    assert c.elements == {"Al": None, "Cu": 4.0, "Mg": 1.0}
    # span points at the real substring
    assert text[c.span[0] : c.span[1]] == "Al-4Cu-1Mg"


def test_dash_notation_steel() -> None:
    comps = extract_compositions("Нержавеющая сталь Fe-18Cr-8Ni широко применяется.")
    dash = [c for c in comps if c.kind == "dash"]
    assert dash and dash[0].element_symbols() == ["Cr", "Fe", "Ni"]
    assert dash[0].elements["Cr"] == 18.0


def test_element_percent_run() -> None:
    comps = extract_compositions("Состав: Fe 65%, Cr 18%, Ni 8%.")
    pct = [c for c in comps if c.kind == "percent"]
    assert pct
    assert pct[0].elements == {"Fe": 65.0, "Cr": 18.0, "Ni": 8.0}
    assert pct[0].base_element == "Fe"


def test_russian_element_name_and_decimal_comma() -> None:
    comps = extract_compositions("Катодная медь 99,9 % чистоты.")
    pct = [c for c in comps if c.kind == "percent"]
    assert pct and pct[0].elements == {"Cu": 99.9}


def test_rejects_non_elements_and_lone_symbols() -> None:
    # "Xx-2Yy" is not a real composition; a lone "Al" is not either.
    assert extract_compositions("параметр Xx-2Yy равен нулю") == []
    assert not [c for c in extract_compositions("образец Al был испытан") if c.kind == "dash"]

"""Tests for the atmosphere canonicalizer (§6.5).

Real, hand-checkable cases covering EN long/short symbols and phrases, RU stems,
the reactivity mapping, and the frozen-dataclass contract.
"""

from __future__ import annotations

from kg_extractors.atmosphere_normalize import (
    AtmosphereNorm,
    normalize_atmosphere,
)

_CANONICAL = {
    "air",
    "argon",
    "nitrogen",
    "vacuum",
    "hydrogen",
    "helium",
    "oxygen",
    "co2",
    "unknown",
}
_REACTIVITY = {"inert", "oxidizing", "reducing", "vacuum", "unknown"}


def test_argon_phrase_is_inert() -> None:
    norm = normalize_atmosphere("annealed in argon")
    assert norm.canonical == "argon"
    assert norm.reactivity == "inert"


def test_argon_short_symbol() -> None:
    assert normalize_atmosphere("Ar atmosphere").canonical == "argon"


def test_ar_boundary_does_not_fire_inside_air() -> None:
    # «in air» must resolve to air, not argon (\bAr\b must not match «air»).
    norm = normalize_atmosphere("in air")
    assert norm.canonical == "air"
    assert norm.reactivity == "oxidizing"


def test_under_vacuum() -> None:
    norm = normalize_atmosphere("under vacuum")
    assert norm.canonical == "vacuum"
    assert norm.reactivity == "vacuum"


def test_nitrogen_flow_short() -> None:
    assert normalize_atmosphere("N2 flow").canonical == "nitrogen"


def test_nitrogen_is_inert() -> None:
    assert normalize_atmosphere("N2 flow").reactivity == "inert"


def test_hydrogen_short_is_reducing() -> None:
    norm = normalize_atmosphere("H2")
    assert norm.canonical == "hydrogen"
    assert norm.reactivity == "reducing"


def test_o2_not_confused_with_co2() -> None:
    # \bO2\b must not fire inside «CO2».
    assert normalize_atmosphere("sintered in CO2").canonical == "co2"
    assert normalize_atmosphere("O2 partial pressure").canonical == "oxygen"


def test_helium_is_inert() -> None:
    norm = normalize_atmosphere("helium atmosphere")
    assert norm.canonical == "helium"
    assert norm.reactivity == "inert"


def test_russian_argon_stem() -> None:
    assert normalize_atmosphere("отжиг в аргоне").canonical == "argon"


def test_unknown_when_no_cue() -> None:
    norm = normalize_atmosphere("quenched somehow")
    assert norm.canonical == "unknown"
    assert norm.reactivity == "unknown"


def test_empty_text_is_unknown() -> None:
    assert normalize_atmosphere("").canonical == "unknown"


def test_as_dict_keys_exact() -> None:
    assert set(normalize_atmosphere("air").as_dict()) == {
        "raw",
        "canonical",
        "reactivity",
    }


def test_as_dict_values_roundtrip() -> None:
    d = normalize_atmosphere("in air").as_dict()
    assert d == {"raw": "in air", "canonical": "air", "reactivity": "oxidizing"}


def test_frozen_dataclass_immutable() -> None:
    norm = normalize_atmosphere("air")
    try:
        norm.canonical = "argon"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - guards the frozen contract
        raise AssertionError("AtmosphereNorm must be frozen")


def test_all_canonical_ids_map_to_valid_reactivity() -> None:
    samples = {
        "annealed in argon": ("argon", "inert"),
        "Ar atmosphere": ("argon", "inert"),
        "under vacuum": ("vacuum", "vacuum"),
        "in air": ("air", "oxidizing"),
        "N2 flow": ("nitrogen", "inert"),
        "H2": ("hydrogen", "reducing"),
        "helium atmosphere": ("helium", "inert"),
        "O2 rich": ("oxygen", "oxidizing"),
        "fired in CO2": ("co2", "oxidizing"),
        "quenched somehow": ("unknown", "unknown"),
    }
    for text, (canonical, reactivity) in samples.items():
        norm = normalize_atmosphere(text)
        assert isinstance(norm, AtmosphereNorm)
        assert norm.canonical == canonical
        assert norm.canonical in _CANONICAL
        assert norm.reactivity == reactivity
        assert norm.reactivity in _REACTIVITY

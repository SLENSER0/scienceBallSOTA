"""Canonical unit registry — dimensions + RU/EN aliases (§7.11)."""

from __future__ import annotations

import pytest

from kg_common.units.registry import (
    DIMENSIONS,
    UNIT_REGISTRY,
    UnitDef,
    dimension_of,
    registry_version,
    resolve_alias,
)


def test_ru_pressure_alias_resolves_to_mpa() -> None:
    # §7.11: cyrillic «МПа» (and lowercase/latin spellings) fold onto canonical MPa.
    assert resolve_alias("МПа") == "MPa"
    assert resolve_alias("мпа") == "MPa"
    assert resolve_alias("mpa") == "MPa"
    assert resolve_alias("MPa") == "MPa"  # canonical resolves to itself


def test_degc_resolves_and_is_temperature() -> None:
    # «degC» / «°C» / cyrillic «°С» all name the canonical temperature unit degC.
    assert resolve_alias("degC") == "degC"
    assert resolve_alias("°C") == "degC"
    assert resolve_alias("°С") == "degC"  # cyrillic es, not latin C
    assert dimension_of("degC") == "temperature"


def test_current_density_a_per_m2() -> None:
    # А/м² (superscript, cyrillic) and a/m2/a/m^2 fold to canonical A/m^2.
    assert resolve_alias("А/м²") == "A/m^2"
    assert resolve_alias("a/m2") == "A/m^2"
    assert resolve_alias("A/m^2") == "A/m^2"
    assert dimension_of("A/m^2") == "current_density"
    assert dimension_of("мА/см2") == "current_density"


def test_unknown_alias_returns_none() -> None:
    # Unregistered units (and empty / None) resolve to None, not to a guess.
    assert resolve_alias("banana") is None
    assert resolve_alias("psi") is None  # a real unit, but outside this registry
    assert resolve_alias("") is None
    assert resolve_alias(None) is None


def test_dimension_of_covers_each_family() -> None:
    assert dimension_of("MPa") == "pressure"
    assert dimension_of("K") == "temperature"
    assert dimension_of("mm") == "length"
    assert dimension_of("%") == "mass_fraction"
    assert dimension_of("mA/cm^2") == "current_density"
    with pytest.raises(ValueError, match="unknown unit"):
        dimension_of("banana")


def test_registry_version_is_deterministic() -> None:
    # Stable content hash: identical across calls, prefixed + 16 hex chars.
    v1 = registry_version()
    v2 = registry_version()
    assert v1 == v2
    assert v1.startswith("ur1:")
    hexpart = v1.split(":", 1)[1]
    assert len(hexpart) == 16
    assert all(c in "0123456789abcdef" for c in hexpart)


def test_aliases_include_ru_forms() -> None:
    # Registry entries carry кириллица aliases, and those aliases actually resolve.
    assert "МПа" in UNIT_REGISTRY["MPa"].aliases
    assert "мкм" in UNIT_REGISTRY["um"].aliases
    assert "А/м2" in UNIT_REGISTRY["A/m^2"].aliases
    assert resolve_alias("мкм") == "um"
    assert resolve_alias("бар") == "bar"
    assert resolve_alias("нм") == "nm"


def test_unit_def_as_dict_shape() -> None:
    d = UNIT_REGISTRY["A/m^2"].as_dict()
    assert set(d) == {"canonical", "dimension", "aliases", "si_factor"}
    assert d["canonical"] == "A/m^2"
    assert d["dimension"] == "current_density"
    assert d["si_factor"] == 1.0
    assert isinstance(d["aliases"], list) and "А/м2" in d["aliases"]


def test_si_factors_are_hand_checked() -> None:
    # SI base is Pa / K / m / fraction / (A/m^2); factor scales onto that base.
    assert UNIT_REGISTRY["MPa"].si_factor == 1_000_000.0  # 1 MPa = 1e6 Pa
    assert UNIT_REGISTRY["kPa"].si_factor == 1_000.0
    assert UNIT_REGISTRY["bar"].si_factor == 100_000.0  # 1 bar = 1e5 Pa
    assert UNIT_REGISTRY["mm"].si_factor == 1e-3
    assert UNIT_REGISTRY["um"].si_factor == 1e-6
    assert UNIT_REGISTRY["%"].si_factor == 1e-2  # 1% = 0.01 fraction
    assert UNIT_REGISTRY["ppm"].si_factor == 1e-6
    assert UNIT_REGISTRY["A/m^2"].si_factor == 1.0
    assert UNIT_REGISTRY["mA/cm^2"].si_factor == 10.0  # 1 mA/cm^2 = 10 A/m^2


def test_registry_covers_all_five_families() -> None:
    present = {ud.dimension for ud in UNIT_REGISTRY.values()}
    assert present == set(DIMENSIONS)
    assert present == {
        "pressure",
        "temperature",
        "length",
        "mass_fraction",
        "current_density",
    }


def test_nfkc_folding_and_whitespace() -> None:
    # NFKC: micro sign µ (U+00B5) ≡ μ; superscript ² ≡ 2; surrounding spaces dropped.
    assert resolve_alias("µm") == "um"
    assert resolve_alias(" MPa ") == "MPa"
    assert resolve_alias("A/m²") == "A/m^2"


def test_every_canonical_resolves_to_itself() -> None:
    for canonical, unit_def in UNIT_REGISTRY.items():
        assert isinstance(unit_def, UnitDef)
        assert resolve_alias(canonical) == canonical
        assert unit_def.dimension in DIMENSIONS

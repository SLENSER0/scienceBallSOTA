"""Property-name normalization to the controlled vocabulary (§6.9)."""

from __future__ import annotations

from kg_extractors.property_normalize import (
    PropertyNorm,
    normalize_property,
)


def test_ru_hardness_maps_to_hardness_id() -> None:
    # твёрдость -> canonical hardness id, exact hit (score 1.0).
    norm = normalize_property("твёрдость")
    assert norm is not None
    assert norm.property_id == "prop:hardness"
    assert norm.canonical == "hardness"
    assert norm.score == 1.0


def test_en_hardness_maps_to_hardness_id() -> None:
    norm = normalize_property("hardness")
    assert norm is not None
    assert norm.property_id == "prop:hardness"
    assert norm.matched_synonym == "hardness"
    assert norm.score == 1.0


def test_microhardness_ru_folds_yo_to_hardness() -> None:
    # микротвёрдость (with ё) folds to the микротвердость synonym -> exact hit.
    norm = normalize_property("микротвёрдость")
    assert norm is not None
    assert norm.property_id == "prop:hardness"
    assert norm.matched_synonym == "микротвердость"
    assert norm.score == 1.0


def test_ru_tensile_maps_to_tensile_strength() -> None:
    # предел прочности -> tensile strength id.
    norm = normalize_property("предел прочности")
    assert norm is not None
    assert norm.property_id == "prop:tensile_strength"
    assert norm.canonical == "tensile strength"
    assert norm.matched_synonym == "предел прочности"


def test_en_conductivity_maps_to_conductivity() -> None:
    norm = normalize_property("conductivity")
    assert norm is not None
    assert norm.property_id == "prop:conductivity"
    assert norm.canonical == "electrical conductivity"
    assert norm.matched_synonym == "conductivity"
    assert norm.score == 1.0


def test_ru_conductivity_maps_to_conductivity() -> None:
    norm = normalize_property("электропроводность")
    assert norm is not None
    assert norm.property_id == "prop:conductivity"


def test_fuzzy_near_miss_typo_maps_to_hardness() -> None:
    # a one-letter typo is caught by the fuzzy stage, with 0.85 <= score < 1.0.
    norm = normalize_property("hardnes")
    assert norm is not None
    assert norm.property_id == "prop:hardness"
    assert norm.matched_synonym == "hardness"
    assert 0.85 <= norm.score < 1.0


def test_matched_synonym_is_the_vocab_surface() -> None:
    # a non-canonical synonym still reports the exact vocab surface it matched.
    norm = normalize_property("proof stress")
    assert norm is not None
    assert norm.property_id == "prop:yield_strength"
    assert norm.matched_synonym == "proof stress"
    assert norm.score == 1.0


def test_unknown_and_blank_return_none() -> None:
    assert normalize_property("несуществующее свойство") is None
    assert normalize_property("banana") is None
    assert normalize_property("") is None
    assert normalize_property("   ") is None
    # a short RU stem below the fuzzy floor must not falsely match (плотность ~0.71).
    assert normalize_property("прочност") is None


def test_as_dict_shape_and_values() -> None:
    norm = normalize_property("Hardness")  # case-insensitive exact
    assert isinstance(norm, PropertyNorm)
    assert norm.as_dict() == {
        "property_id": "prop:hardness",
        "canonical": "hardness",
        "matched_synonym": "hardness",
        "score": 1.0,
    }

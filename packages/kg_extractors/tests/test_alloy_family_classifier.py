"""Composition-driven alloy-family classification tests (§8.3)."""

from __future__ import annotations

from kg_extractors.alloy_family_classifier import AlloyFamily, classify_from_composition

# ---------------------------------------------------------------------------
# Aluminium AA series — dominant alloying element (§8.3)
# ---------------------------------------------------------------------------


def test_al_cu_is_2xxx() -> None:
    result = classify_from_composition({"Al": 95.5, "Cu": 4.5})
    assert result.base_element == "Al"
    assert result.family == "2xxx"
    assert result.subfamily is None


def test_al_zn_mg_is_7xxx() -> None:
    # 7075-like: Zn dominant over Mg → 7xxx (not 5xxx/6xxx).
    assert classify_from_composition({"Al": 90, "Zn": 5.6, "Mg": 2.5}).family == "7xxx"


def test_al_mg_si_is_6xxx() -> None:
    # 6061-like: Mg dominant with Si present → magnesium-silicide 6xxx.
    assert classify_from_composition({"Al": 97.9, "Mg": 1.0, "Si": 0.6}).family == "6xxx"


def test_al_mg_only_is_5xxx() -> None:
    assert classify_from_composition({"Al": 95, "Mg": 4.5}).family == "5xxx"


def test_al_mn_is_3xxx() -> None:
    assert classify_from_composition({"Al": 98.8, "Mn": 1.2}).family == "3xxx"


def test_al_si_only_is_4xxx() -> None:
    assert classify_from_composition({"Al": 88, "Si": 12}).family == "4xxx"


def test_al_pure_is_1xxx() -> None:
    assert classify_from_composition({"Al": 99.7}).family == "1xxx"


# ---------------------------------------------------------------------------
# Iron-based — stainless vs carbon steel (§8.3)
# ---------------------------------------------------------------------------


def test_fe_cr_ni_is_austenitic_stainless() -> None:
    result = classify_from_composition({"Fe": 70, "Cr": 18, "Ni": 10})
    assert result.family == "stainless_steel"
    assert result.subfamily == "austenitic"


def test_fe_cr_low_ni_is_ferritic_martensitic() -> None:
    result = classify_from_composition({"Fe": 85, "Cr": 13})
    assert result.family == "stainless_steel"
    assert result.subfamily == "ferritic_martensitic"


def test_fe_cr_below_threshold_is_carbon_steel() -> None:
    assert classify_from_composition({"Fe": 98, "C": 0.4}).family == "carbon_steel"


def test_fe_cr_exactly_at_threshold_is_stainless() -> None:
    # 10.5 wt% Cr is the boundary and counts as stainless (inclusive).
    assert classify_from_composition({"Fe": 89.5, "Cr": 10.5}).family == "stainless_steel"


# ---------------------------------------------------------------------------
# Titanium / nickel / unknown (§8.3)
# ---------------------------------------------------------------------------


def test_titanium_alloy() -> None:
    assert classify_from_composition({"Ti": 90, "Al": 6, "V": 4}).family == "titanium_alloy"


def test_nickel_superalloy() -> None:
    result = classify_from_composition({"Ni": 60, "Cr": 20, "Fe": 15})
    assert result.base_element == "Ni"
    assert result.family == "nickel_superalloy"


def test_empty_composition_is_unknown() -> None:
    result = classify_from_composition({})
    assert result.base_element is None
    assert result.family == "unknown"
    assert result.confidence == 0.0


def test_unrecognized_base_is_unknown() -> None:
    result = classify_from_composition({"Cu": 90, "Zn": 10})
    assert result.base_element == "Cu"
    assert result.family == "unknown"


# ---------------------------------------------------------------------------
# Confidence + serialization contract (§8.3)
# ---------------------------------------------------------------------------


def test_confidence_is_base_dominance_float() -> None:
    result = classify_from_composition({"Al": 95.5, "Cu": 4.5})
    assert isinstance(result.confidence, float)
    assert result.confidence == 0.955  # 95.5 / 100.0


def test_as_dict_shape_and_confidence_float() -> None:
    result = classify_from_composition({"Fe": 70, "Cr": 18, "Ni": 10})
    payload = result.as_dict()
    assert set(payload) == {"base_element", "family", "subfamily", "confidence"}
    assert isinstance(payload["confidence"], float)


def test_alloy_family_is_frozen() -> None:
    fam = AlloyFamily(base_element="Ti", family="titanium_alloy", subfamily=None, confidence=0.9)
    try:
        fam.family = "steel"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("AlloyFamily must be frozen/immutable")

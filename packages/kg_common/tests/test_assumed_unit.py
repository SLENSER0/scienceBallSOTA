"""Tests for name-embedded assumed units (§7.2).

Verify that a unit is taken only when the property name explicitly spells it as
a suffix/token, that the ``unit_assumed`` flag / ``'rule'`` method always ride
along, and that cyrillic pressure spellings fold to their ASCII canonical.

Тесты §7.2: единица берётся только если явно зашита в имя свойства.
"""

from __future__ import annotations

from kg_common.units.assumed_unit import AssumedUnit, embedded_unit


def test_hardness_hv_suffix() -> None:
    """``hardness_HV`` → ``HV`` and is flagged as an assumption."""
    result = embedded_unit("hardness_HV")
    assert result.assumed_unit == "HV"
    assert result.unit_assumed is True


def test_yield_strength_mpa_suffix() -> None:
    """A multi-token name still finds the trailing ``MPa`` token."""
    assert embedded_unit("yield_strength_MPa").assumed_unit == "MPa"


def test_temperature_c_ascii_not_degc() -> None:
    """ASCII ``C`` is taken verbatim, not folded to the registry ``degC``."""
    assert embedded_unit("temperature_C").assumed_unit == "C"


def test_no_unit_in_name() -> None:
    """A bare name names no unit: nothing is assumed."""
    result = embedded_unit("hardness")
    assert result.assumed_unit is None
    assert result.unit_assumed is False


def test_normalization_method_is_rule() -> None:
    """A name-embedded assumption always carries ``normalization_method='rule'``."""
    assert embedded_unit("hardness_HV").normalization_method == "rule"


def test_no_unit_has_no_method() -> None:
    """When nothing is assumed the normalization method is ``None``."""
    assert embedded_unit("hardness").normalization_method is None


def test_cyrillic_gpa_folds_to_ascii() -> None:
    """Cyrillic ``ГПа`` folds to the ASCII canonical ``GPa`` (§7.2)."""
    assert embedded_unit("prop_ГПа").assumed_unit == "GPa"


def test_cyrillic_mpa_folds_via_resolve_alias() -> None:
    """Cyrillic ``МПа`` folds to ``MPa`` through the registry alias table."""
    assert embedded_unit("strength_МПа").assumed_unit == "MPa"


def test_space_separator() -> None:
    """A space is a valid token separator, not only the underscore."""
    result = embedded_unit("hardness HRC")
    assert result.assumed_unit == "HRC"
    assert result.unit_assumed is True


def test_rightmost_token_wins() -> None:
    """When two tokens name units the trailing (suffix) one is chosen."""
    assert embedded_unit("K_hardness_HB").assumed_unit == "HB"


def test_lowercase_word_not_mistaken_for_unit() -> None:
    """A lowercase ``c`` word token is not matched as the Celsius unit."""
    result = embedded_unit("specific_heat_c")
    assert result.assumed_unit is None
    assert result.unit_assumed is False


def test_as_dict_roundtrip() -> None:
    """``as_dict`` exposes every field for JSON-friendly serialisation."""
    result = embedded_unit("hardness_HV")
    assert result.as_dict() == {
        "property_name": "hardness_HV",
        "assumed_unit": "HV",
        "unit_assumed": True,
        "normalization_method": "rule",
    }


def test_frozen_dataclass_is_immutable() -> None:
    """:class:`AssumedUnit` is frozen — assumptions cannot be mutated in place."""
    result = embedded_unit("hardness_HV")
    assert isinstance(result, AssumedUnit)
    try:
        result.assumed_unit = "HRC"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("AssumedUnit should be immutable")

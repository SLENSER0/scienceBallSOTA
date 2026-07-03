"""Tests for the §17.8 graph query template preset registry.

Проверяем реестр шаблонов сайдбара графа: схему полей, доступ по ключу,
уникальность ключей и сборку тела запроса §6.2 из значений формы (умолчания и
обязательные поля).

Covers the field schema, keyed lookup, key uniqueness, and building a §6.2
request body from form values (defaults and required-field enforcement).
"""

from __future__ import annotations

import pytest
from api_gateway.graph_query_presets import (
    PresetField,
    QueryPreset,
    build_request,
    get_preset,
    list_presets,
)


def test_preset_field_as_dict() -> None:
    """PresetField.as_dict — плоский вид схемы / flat schema view."""
    assert PresetField("material", "string", True, None).as_dict() == {
        "name": "material",
        "type": "string",
        "required": True,
        "default": None,
    }


def test_query_preset_as_dict_serializes_fields() -> None:
    """QueryPreset.as_dict — поля как кортеж dict / fields as tuple of dicts."""
    preset = get_preset("material_regime_property")
    assert preset is not None
    data = preset.as_dict()
    assert data["key"] == "material_regime_property"
    assert data["query_type"] == "material_regime_property"
    assert isinstance(data["fields"], tuple)
    assert data["fields"][0] == {
        "name": "material",
        "type": "string",
        "required": True,
        "default": None,
    }


def test_get_preset_known_query_type() -> None:
    """get_preset даёт ожидаемый query_type / known preset query_type."""
    preset = get_preset("material_regime_property")
    assert preset is not None
    assert preset.query_type == "material_regime_property"


def test_get_preset_unknown_is_none() -> None:
    """Неизвестный ключ → None / unknown key returns None."""
    assert get_preset("nope") is None


def test_list_presets_nonempty_unique_keys() -> None:
    """Реестр непуст и ключи уникальны / non-empty, unique keys."""
    presets = list_presets()
    assert presets
    keys = [preset.key for preset in presets]
    assert len(keys) == len(set(keys))
    assert all(isinstance(preset, QueryPreset) for preset in presets)


def test_material_regime_property_fields() -> None:
    """Пресет содержит требуемые поля §17.8 / preset has the required fields."""
    preset = get_preset("material_regime_property")
    assert preset is not None
    names = [field.name for field in preset.fields]
    assert names == ["material", "operation", "temperature_c", "property"]
    material = preset.fields[0]
    assert material.required is True


def test_build_request_maps_top_level_values() -> None:
    """build_request кладёт material/property наверх / top-level mapping."""
    request = build_request(
        "material_regime_property", {"material": "Al-Cu", "property": "hardness"}
    )
    assert request["query_type"] == "material_regime_property"
    assert request["material"] == "Al-Cu"
    assert request["property"] == "hardness"


def test_build_request_missing_required_raises() -> None:
    """Отсутствие обязательного material → ValueError / required missing."""
    with pytest.raises(ValueError):
        build_request("material_regime_property", {"property": "hardness"})


def test_build_request_applies_optional_default() -> None:
    """Умолчание опционального поля попадает в тело / default appears."""
    request = build_request("material_regime_property", {"material": "Al-Cu"})
    # ``operation`` defaults to ``'aging'`` and is a §6.2 processing sub-field.
    assert request["processing"] == {"operation": "aging"}


def test_build_request_processing_and_top_level_split() -> None:
    """operation/temperature_c → processing, остальное наверх / split."""
    request = build_request(
        "material_regime_property",
        {
            "material": "Al-Cu",
            "operation": "solutionizing",
            "temperature_c": 530,
            "property": "hardness",
        },
    )
    assert request["material"] == "Al-Cu"
    assert request["property"] == "hardness"
    assert request["processing"] == {"operation": "solutionizing", "temperature_c": 530}


def test_build_request_unknown_preset_raises() -> None:
    """Неизвестный пресет в build_request → ValueError / unknown preset."""
    with pytest.raises(ValueError):
        build_request("nope", {"material": "Al-Cu"})

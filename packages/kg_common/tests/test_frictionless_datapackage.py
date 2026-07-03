"""Tests for §22.6 Frictionless datapackage.json descriptor builder.

Проверяют вывод типов (:func:`infer_field_type`), сборку ресурса/пакета и
round-trip JSON. Значения подобраны так, чтобы результат был проверяем руками
(hand-checkable): целые/дробные/смешанные колонки и опускание ``created``.
"""

from __future__ import annotations

import json

from kg_common.frictionless_datapackage import (
    DataPackage,
    Field,
    Resource,
    build_datapackage,
    build_resource,
    infer_field_type,
    to_json,
)


def test_infer_integer() -> None:
    # Assertion (1): все значения — целые.
    assert infer_field_type(["1", "2"]) == "integer"


def test_infer_number() -> None:
    # Assertion (2): есть дробное → number.
    assert infer_field_type(["1.5", "2"]) == "number"


def test_infer_mixed_is_string() -> None:
    # Assertion (3): нечисловое значение → string.
    assert infer_field_type(["1", "x"]) == "string"


def test_infer_boolean() -> None:
    # Булевы литералы (не пересекаются с integer-набором) → boolean.
    assert infer_field_type(["true", "false", "yes"]) == "boolean"


def test_infer_empty_is_string() -> None:
    # Пустая колонка / только пустые строки → безопасный string.
    assert infer_field_type([]) == "string"
    assert infer_field_type(["", "  "]) == "string"


def test_infer_zero_one_are_integer_not_boolean() -> None:
    # ['0','1'] должны считаться целыми, а не булевыми (integer раньше boolean).
    assert infer_field_type(["0", "1"]) == "integer"


def test_build_resource_single_field() -> None:
    # Assertion (4): одна строка {'a':'1'} → один Field('a','integer'), rowcount 1.
    resource = build_resource("t", "data/t.csv", [{"a": "1"}])
    assert resource.fields == (Field("a", "integer"),)
    assert resource.rowcount == 1
    assert resource.path == "data/t.csv"


def test_build_resource_first_seen_column_order() -> None:
    rows = [{"b": "1", "a": "2.5"}, {"a": "3", "c": "x"}]
    resource = build_resource("r", "data/r.csv", rows)
    # Порядок колонок — first-seen: b, a, c.
    assert [f.name for f in resource.fields] == ["b", "a", "c"]
    types = {f.name: f.type for f in resource.fields}
    assert types == {"b": "integer", "a": "number", "c": "string"}
    assert resource.rowcount == 2


def test_resource_as_dict_profile_and_schema() -> None:
    # Assertion (5): resource profile == 'tabular-data-resource', есть schema.fields.
    resource = build_resource("t", "data/t.csv", [{"a": "1"}])
    payload = resource.as_dict()
    assert payload["profile"] == "tabular-data-resource"
    assert payload["schema"]["fields"] == [{"name": "a", "type": "integer"}]
    assert payload["rowcount"] == 1


def test_datapackage_as_dict_profile_and_resources_list() -> None:
    # Assertions (5)+(6): package profile 'tabular-data-package', resources — список dict.
    resource = build_resource("t", "data/t.csv", [{"a": "1"}])
    pkg = build_datapackage("bundle", [resource], created="2026-07-03T00:00:00Z")
    payload = pkg.as_dict()
    assert payload["profile"] == "tabular-data-package"
    assert isinstance(payload["resources"], list)
    assert payload["resources"] == [resource.as_dict()]
    assert payload["created"] == "2026-07-03T00:00:00Z"


def test_created_none_omits_key() -> None:
    # Assertion (7): created=None → ключ 'created' отсутствует.
    pkg = build_datapackage("bundle", [], created=None)
    payload = pkg.as_dict()
    assert "created" not in payload
    # Значение по умолчанию тоже опускает ключ.
    assert "created" not in DataPackage("b", ()).as_dict()


def test_to_json_round_trip_preserves_path() -> None:
    # Assertion (8): to_json парсится обратно, путь ресурса сохранён.
    resource = build_resource("t", "data/t.csv", [{"a": "1", "b": "1.5"}])
    pkg = build_datapackage("bundle", [resource])
    text = to_json(pkg)
    parsed = json.loads(text)
    assert parsed["resources"][0]["path"] == "data/t.csv"
    assert parsed["name"] == "bundle"
    assert parsed["resources"][0]["schema"]["fields"] == [
        {"name": "a", "type": "integer"},
        {"name": "b", "type": "number"},
    ]


def test_to_json_deterministic() -> None:
    resource = build_resource("t", "data/t.csv", [{"a": "1"}])
    pkg = build_datapackage("bundle", [resource], created="2026-01-01T00:00:00Z")
    assert to_json(pkg) == to_json(pkg)


def test_field_and_resource_are_frozen() -> None:
    field = Field("a", "integer")
    resource = Resource("t", "p.csv", (field,), 0)
    for obj, attr in ((field, "name"), (resource, "path")):
        try:
            setattr(obj, attr, "mutated")
        except AttributeError:
            continue
        raise AssertionError("frozen dataclass unexpectedly mutable")

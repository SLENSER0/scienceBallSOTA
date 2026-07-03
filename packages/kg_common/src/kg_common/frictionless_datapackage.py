"""Frictionless *datapackage.json* descriptor builder (§22.6 self-describing export).

Чистый, безсетевой построитель дескриптора `Frictionless Data Package
<https://specs.frictionlessdata.io/>`_ (``datapackage.json``) для набора
экспортированных CSV-ресурсов. Каждый ресурс описывается именем, путём к файлу,
табличной схемой (:class:`Field` c выведенным типом) и числом строк
(``rowcount``), так что выгрузка KG (KG export bundle) становится
самоописываемой (self-describing) без внешних зависимостей — только stdlib
``json`` и frozen-dataclasses.

Типы полей выводятся из строковых значений колонки (:func:`infer_field_type`):
все значения — целые → ``"integer"``; все числовые (хотя бы одно дробное) →
``"number"``; все булевы → ``"boolean"``; иначе → ``"string"``. Пустой набор
значений трактуется как ``"string"`` (safe default). :func:`build_resource`
собирает :class:`Resource` из строк-словарей (columns в порядке first-seen),
:func:`build_datapackage` — контейнер :class:`DataPackage`, а :func:`to_json`
даёт детерминированный round-trippable JSON.

Модуль ничего не читает из графа и не меняет существующих файлов — он работает
поверх уже выгруженных строк (rows) как чистая функция.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "DataPackage",
    "Field",
    "Resource",
    "build_datapackage",
    "build_resource",
    "infer_field_type",
    "to_json",
]

# Frictionless profiles (профили спецификации).
_PACKAGE_PROFILE = "tabular-data-package"
_RESOURCE_PROFILE = "tabular-data-resource"

# Строковые литералы булевых значений (case-insensitive).
_BOOLEAN_TRUE = frozenset({"true", "1", "yes"})
_BOOLEAN_FALSE = frozenset({"false", "0", "no"})


@dataclass(frozen=True)
class Field:
    """Одна колонка табличной схемы — имя + выведенный тип (§22.6).

    ``type`` — один из ``"integer"`` / ``"number"`` / ``"boolean"`` /
    ``"string"`` (Frictionless field types). Frozen, поэтому поле можно свободно
    переиспользовать между ресурсами; :meth:`as_dict` даёт JSON-представление.
    """

    name: str
    type: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.type}


@dataclass(frozen=True)
class Resource:
    """CSV-ресурс пакета — имя, путь, схема и число строк (§22.6).

    ``fields`` — кортеж :class:`Field` в порядке появления колонок (first-seen);
    ``rowcount`` — количество строк данных (без заголовка). :meth:`as_dict`
    включает ``profile == "tabular-data-resource"`` и вложенную
    ``schema.fields``, как того требует Frictionless.
    """

    name: str
    path: str
    fields: tuple[Field, ...]
    rowcount: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "profile": _RESOURCE_PROFILE,
            "rowcount": self.rowcount,
            "schema": {"fields": [f.as_dict() for f in self.fields]},
        }


@dataclass(frozen=True)
class DataPackage:
    """Контейнер-дескриптор ``datapackage.json`` (§22.6 self-describing bundle).

    ``resources`` — кортеж :class:`Resource`; ``created`` — необязательная
    ISO-8601 метка создания. Если ``created is None``, ключ ``"created"`` в
    :meth:`as_dict` опускается (omitted), чтобы дескриптор оставался
    детерминированным при неуказанном времени.
    """

    name: str
    resources: tuple[Resource, ...]
    created: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "profile": _PACKAGE_PROFILE,
            "resources": [r.as_dict() for r in self.resources],
        }
        if self.created is not None:
            payload["created"] = self.created
        return payload


def _is_integer(value: str) -> bool:
    """Строка — целое (integer)? Допускается ведущий знак, но не дробь/экспонента."""
    text = value.strip()
    if not text:
        return False
    body = text[1:] if text[0] in "+-" else text
    return body.isdigit()


def _is_number(value: str) -> bool:
    """Строка — число (number, float/int)? Через попытку ``float()`` без inf/nan."""
    text = value.strip()
    if not text:
        return False
    if text.lower().lstrip("+-") in {"inf", "infinity", "nan"}:
        return False
    try:
        float(text)
    except ValueError:
        return False
    return True


def _is_boolean(value: str) -> bool:
    """Строка — булево (boolean)? Из фиксированного набора литералов, case-insensitive."""
    text = value.strip().lower()
    return text in _BOOLEAN_TRUE or text in _BOOLEAN_FALSE


def infer_field_type(values: Iterable[str]) -> str:
    """Вывести Frictionless-тип колонки из её строковых значений (§22.6).

    Правила (в порядке приоритета): все значения — целые → ``"integer"``; все
    булевы → ``"boolean"``; все числовые (integer/float) → ``"number"``; иначе
    → ``"string"``. Пустая колонка или колонка только из пустых строк даёт
    безопасный ``"string"``. ``integer`` проверяется до ``boolean``, чтобы
    ``['0', '1']`` считалось целыми числами, а не булевыми.
    """
    non_empty = [v for v in values if v.strip() != ""]
    if not non_empty:
        return "string"
    if all(_is_integer(v) for v in non_empty):
        return "integer"
    if all(_is_boolean(v) for v in non_empty):
        return "boolean"
    if all(_is_number(v) for v in non_empty):
        return "number"
    return "string"


def build_resource(name: str, path: str, rows: Sequence[dict[str, Any]]) -> Resource:
    """Собрать :class:`Resource` из строк-словарей (§22.6).

    Колонки берутся в порядке first-seen по всем строкам ``rows`` (стабильно,
    детерминированно). Для каждой колонки значения приводятся к ``str`` и
    прогоняются через :func:`infer_field_type`; отсутствующие в строке ключи
    пропускаются при выводе типа. ``rowcount == len(rows)``.
    """
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    fields = tuple(
        Field(name=col, type=infer_field_type(str(row[col]) for row in rows if col in row))
        for col in columns
    )
    return Resource(name=name, path=path, fields=fields, rowcount=len(rows))


def build_datapackage(
    name: str,
    resources: Sequence[Resource],
    *,
    created: str | None = None,
) -> DataPackage:
    """Собрать :class:`DataPackage` из готовых ресурсов (§22.6).

    Просто оборачивает ``resources`` в frozen-контейнер; ``created`` пробрасывается
    как есть (``None`` → ключ будет опущен в :meth:`DataPackage.as_dict`).
    """
    return DataPackage(name=name, resources=tuple(resources), created=created)


def to_json(pkg: DataPackage, *, indent: int = 2) -> str:
    """Сериализовать дескриптор в детерминированный JSON (§22.6).

    Ключи сортируются (``sort_keys=True``), поэтому одинаковый пакет даёт
    побайтово одинаковый вывод; ``json.loads(to_json(pkg))`` восстанавливает ту
    же структуру (round-trip). ``indent`` управляет человекочитаемым отступом.
    """
    return json.dumps(pkg.as_dict(), sort_keys=True, ensure_ascii=False, indent=indent)

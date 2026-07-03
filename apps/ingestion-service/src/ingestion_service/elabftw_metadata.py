"""Parse eLabFTW ``extra_fields`` JSON metadata into normalized domain fields (§20.4).

eLabFTW (§20.4) stores structured experiment metadata as a JSON ``metadata`` blob whose
``extra_fields`` object maps a human field name to a ``{"value", "unit", "group"}`` record.
This module turns that loosely-typed blob into typed, frozen domain objects so downstream
ingestion (§20.1/§20.3) can anchor Material/ProcessingRegime/Measurement nodes without
re-parsing raw JSON.

Разбор метаданных eLabFTW (``extra_fields``) в нормализованные доменные поля: материал,
температура, время, атмосфера, оборудование и измеряемое свойство.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _to_float(value: Any) -> float | None:
    """Best-effort numeric coercion (RU decimal comma tolerated); None on failure.

    Мягкое приведение к float: поддерживает запятую как десятичный разделитель.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class ElabField:
    """One eLabFTW ``extra_fields`` entry: name plus value/unit/group (§20.4)."""

    name: str
    value: str = ""
    unit: str = ""
    group: str = ""

    def as_dict(self) -> dict[str, str]:
        """Serialise this field to a plain JSON-safe dict."""
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "group": self.group,
        }


@dataclass(frozen=True, slots=True)
class ElabMetadata:
    """Normalized domain view of an eLabFTW experiment's ``extra_fields`` (§20.4)."""

    material: str = ""
    temperature_c: float | None = None
    time_h: float | None = None
    atmosphere: str = ""
    equipment: str = ""
    measured_property: str = ""
    measured_value: float | None = None
    measured_unit: str = ""
    fields: tuple[ElabField, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        """Serialise the normalized metadata (incl. raw fields) to a plain dict."""
        return {
            "material": self.material,
            "temperature_c": self.temperature_c,
            "time_h": self.time_h,
            "atmosphere": self.atmosphere,
            "equipment": self.equipment,
            "measured_property": self.measured_property,
            "measured_value": self.measured_value,
            "measured_unit": self.measured_unit,
            "fields": [f.as_dict() for f in self.fields],
        }


def parse_extra_fields(metadata: dict[str, Any]) -> list[ElabField]:
    """Read ``metadata['extra_fields']`` (name -> {value,unit,group}) into ElabField list.

    Разбирает блок ``extra_fields`` метаданных eLabFTW в список ElabField. Пустые/
    отсутствующие метаданные дают пустой список.
    """
    extra = metadata.get("extra_fields", {}) if isinstance(metadata, dict) else {}
    if not isinstance(extra, dict):
        return []
    fields: list[ElabField] = []
    for name, record in extra.items():
        rec = record if isinstance(record, dict) else {}
        fields.append(
            ElabField(
                name=str(name),
                value=str(rec.get("value", "") or ""),
                unit=str(rec.get("unit", "") or ""),
                group=str(rec.get("group", "") or ""),
            )
        )
    return fields


def extract_domain(fields: list[ElabField]) -> ElabMetadata:
    """Match field names (case-insensitively) to normalized domain slots (§20.4).

    ``material``/``alloy`` -> material, ``temperature`` -> temperature_c (float),
    ``time`` -> time_h (float), ``atmosphere``/``equipment`` verbatim, and a field named
    ``property`` populates measured_property/measured_value/measured_unit.
    """
    material = ""
    temperature_c: float | None = None
    time_h: float | None = None
    atmosphere = ""
    equipment = ""
    measured_property = ""
    measured_value: float | None = None
    measured_unit = ""

    for f in fields:
        key = f.name.strip().lower()
        if key in ("material", "alloy") and not material:
            material = f.value
        elif key == "temperature" and temperature_c is None:
            temperature_c = _to_float(f.value)
        elif key == "time" and time_h is None:
            time_h = _to_float(f.value)
        elif key == "atmosphere" and not atmosphere:
            atmosphere = f.value
        elif key == "equipment" and not equipment:
            equipment = f.value
        elif key == "property" and not measured_property:
            measured_property = f.value
            measured_value = _to_float(f.value)
            measured_unit = f.unit

    return ElabMetadata(
        material=material,
        temperature_c=temperature_c,
        time_h=time_h,
        atmosphere=atmosphere,
        equipment=equipment,
        measured_property=measured_property,
        measured_value=measured_value,
        measured_unit=measured_unit,
        fields=tuple(fields),
    )

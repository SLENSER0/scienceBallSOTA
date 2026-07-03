"""eLab/LIMS record → internal lab-record shape mapping (§20.5).

Pure, offline field-mapper that sits *in front of* the lab catalog importer
(``lab_import.import_experiment_catalog``, §20.1/§20.4): it takes one raw record
as exported from an ELN/LIMS (eLabFTW, openBIS, …) plus a *mapping* describing
which record keys carry which internal field, and returns the normalized shape::

    {"material": <str|None>, "measurements": [<measurement>, …], "meta": {…}}

Каждое измерение (measurement) — это ``{property, value, unit, date}``. A record
may carry either a single flat measurement (``property``/``value``/``unit`` keys
at the top level) or an explicit ``measurements`` list; both are supported. Every
field is *optional* — missing keys are tolerated and simply yield ``None`` (or an
empty list / empty meta), never an error. Unconsumed record keys are preserved
verbatim under ``meta`` so no source metadata is lost (метаданные сохраняются).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Internal field name → default record key it is read from (§20.5).
DEFAULT_MAPPING: dict[str, str] = {
    "material": "material",
    "property": "property",
    "value": "value",
    "unit": "unit",
    "date": "date",
    "measurements": "measurements",
}


def _clean(value: Any) -> Any:
    """Trim string cells to a non-empty value, pass numbers through, else None."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return value


@dataclass(frozen=True)
class Measurement:
    """One normalized measurement of the internal lab-record shape (§20.5).

    Fields
    ------
    property
        Measured property name (свойство), or ``None``.
    value
        Numeric or raw value, or ``None`` when absent.
    unit
        Unit token, or ``None`` when unitless.
    date
        Actualization date string, or ``None``.
    """

    property: str | None
    value: Any
    unit: str | None
    date: str | None

    def as_dict(self) -> dict[str, Any]:
        """Full structured view (all fields, including ``None``)."""
        return {
            "property": self.property,
            "value": self.value,
            "unit": self.unit,
            "date": self.date,
        }


@dataclass(frozen=True)
class MappedRecord:
    """A raw lab record mapped to the internal shape (§20.5).

    Fields
    ------
    material
        Canonical material name of the record, or ``None`` when absent.
    measurements
        Tuple of :class:`Measurement`; empty when the record carries none.
    meta
        Record keys not consumed by the mapping, preserved verbatim.
    """

    material: str | None
    measurements: tuple[Measurement, ...]
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Full structured view; measurements rendered via their ``as_dict``."""
        return {
            "material": self.material,
            "measurements": [m.as_dict() for m in self.measurements],
            "meta": dict(self.meta),
        }


def _map_measurement(source: dict[str, Any], mapping: dict[str, str]) -> Measurement | None:
    """Build one :class:`Measurement` from *source*; None if every field is empty."""
    prop = _clean(source.get(mapping["property"]))
    value = _clean(source.get(mapping["value"]))
    unit = _clean(source.get(mapping["unit"]))
    date = _clean(source.get(mapping["date"]))
    if prop is None and value is None and unit is None and date is None:
        return None
    return Measurement(property=prop, value=value, unit=unit, date=date)


def map_lab_record(record: dict[str, Any], mapping: dict[str, str] | None = None) -> MappedRecord:
    """Map one raw eLab/LIMS *record* to the internal shape (§20.5).

    *mapping* overrides :data:`DEFAULT_MAPPING` per internal field, so custom ELN
    column names can be routed without touching the record. Measurements come from
    an explicit ``measurements`` list (each item mapped in turn) or, absent that,
    from the flat ``property``/``value``/``unit``/``date`` keys of the record. Any
    record key not named by the mapping is preserved under :attr:`MappedRecord.meta`.
    Every field is optional — a missing key yields ``None`` / an empty collection.
    """
    resolved = {**DEFAULT_MAPPING, **(mapping or {})}

    material = _clean(record.get(resolved["material"]))

    measurements: list[Measurement] = []
    raw_list = record.get(resolved["measurements"])
    if isinstance(raw_list, (list, tuple)):
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            mapped = _map_measurement(item, resolved)
            if mapped is not None:
                measurements.append(mapped)
    else:
        mapped = _map_measurement(record, resolved)
        if mapped is not None:
            measurements.append(mapped)

    consumed = {
        resolved["material"],
        resolved["property"],
        resolved["value"],
        resolved["unit"],
        resolved["date"],
        resolved["measurements"],
    }
    meta = {k: v for k, v in record.items() if k not in consumed}

    return MappedRecord(
        material=material,
        measurements=tuple(measurements),
        meta=meta,
    )

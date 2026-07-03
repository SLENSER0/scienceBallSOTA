"""Aggregate open Gap nodes per entity into a ``missing_fields`` projection (§15.2/§5.3).

RU: ``graph_dto`` только читает ``missing_fields`` узла, но никто не вычисляет это
поле, агрегируя открытые Gap-узлы по сущности. Этот модуль группирует Gap-записи по
``about_entity_id``, отображает ``gap_type`` в имя поля через таблицу
:data:`GAP_TYPE_TO_FIELD` (неизвестные типы пропускаются), сортирует и дедуплицирует
поля. По умолчанию учитываются только открытые (``status != 'resolved'``) гэпы.
EN: ``graph_dto`` only reads a node's ``missing_fields``; nothing computes it by
aggregating open Gap nodes per entity. This module groups Gap records by
``about_entity_id``, maps ``gap_type`` to a field name via :data:`GAP_TYPE_TO_FIELD`
(unknown types are skipped), and sorts + dedupes the resulting fields. By default only
open (``status != 'resolved'``) gaps are counted.

Pure python — no store access. Kuzu note: custom node props are NOT queryable
columns; callers RETURN base columns and read the rest via ``get_node()`` before
handing gap dicts to :func:`project_missing_fields`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# §15.2 gap_type -> node field name. Unknown gap_type values are skipped.
GAP_TYPE_TO_FIELD: dict[str, str] = {
    "missing_unit": "unit",
    "missing_baseline": "baseline_value",
    "missing_source_span": "source_span",
    "missing_processing_parameter": "processing_parameter",
}


@dataclass(frozen=True)
class EntityMissingFields:
    """Frozen per-entity projection of missing fields (§15.2/§5.3).

    ``entity_id`` is the ``about_entity_id`` of the aggregated gaps; ``missing_fields``
    is the sorted, de-duplicated tuple of mapped field names; ``gap_ids`` lists the ids
    of every contributing Gap (order preserved, duplicates kept per gap).
    """

    entity_id: str
    missing_fields: tuple[str, ...]
    gap_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict projection for trace / round-trip (§15.2, house style)."""
        return {
            "entity_id": self.entity_id,
            "missing_fields": list(self.missing_fields),
            "gap_ids": list(self.gap_ids),
        }


def _is_open(gap: dict) -> bool:
    """A gap is open unless its ``status`` is ``'resolved'`` (§15.2)."""
    return gap.get("status") != "resolved"


def project_missing_fields(
    gaps: list[dict], *, open_only: bool = True
) -> dict[str, EntityMissingFields]:
    """Aggregate Gap dicts into per-entity :class:`EntityMissingFields` (§15.2/§5.3).

    RU: Группирует ``gaps`` по ``about_entity_id``; ``gap_type`` отображается в поле
    через :data:`GAP_TYPE_TO_FIELD`; неизвестные типы пропускаются. Сущность без единого
    отображённого поля отсутствует в результате. При ``open_only`` (по умолчанию) гэпы со
    ``status == 'resolved'`` игнорируются.
    EN: Groups ``gaps`` by ``about_entity_id``; ``gap_type`` is mapped to a field via
    :data:`GAP_TYPE_TO_FIELD`; unknown types are skipped. An entity with no mapped field
    is absent from the result. With ``open_only`` (default) gaps whose ``status`` is
    ``'resolved'`` are ignored.
    """
    fields_by_entity: dict[str, set[str]] = {}
    gap_ids_by_entity: dict[str, list[str]] = {}
    for gap in gaps:
        if open_only and not _is_open(gap):
            continue
        field = GAP_TYPE_TO_FIELD.get(gap.get("gap_type"))
        if field is None:
            continue
        entity_id = gap.get("about_entity_id")
        if entity_id is None:
            continue
        fields_by_entity.setdefault(entity_id, set()).add(field)
        gap_ids_by_entity.setdefault(entity_id, []).append(gap.get("gap_id"))

    result: dict[str, EntityMissingFields] = {}
    for entity_id, fields in fields_by_entity.items():
        result[entity_id] = EntityMissingFields(
            entity_id=entity_id,
            missing_fields=tuple(sorted(fields)),
            gap_ids=tuple(gap_ids_by_entity[entity_id]),
        )
    return result

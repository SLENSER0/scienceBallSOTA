"""Группировка/фильтрация противоречий для Gap Dashboard (§5.2.7, §14.8).

Помощник для ``GET /contradictions`` (§5.2.7): противоречия отдаются сырыми
в :mod:`api_gateway.gaps` без группировки. Модуль на чистом stdlib фильтрует
строки по материалу/свойству и группирует их по паре ``(material, property)``,
дедуплицируя ``claim_id`` с сохранением порядка.

Grouping/filtering helper for the §5.2.7 Gap Dashboard ``GET /contradictions``
endpoint: contradictions are surfaced raw in :mod:`api_gateway.gaps` with no
grouping helper. Pure stdlib — filters rows by material/property and groups them
by the ``(material, property)`` pair, deduplicating ``claim_id`` values while
preserving order.

* :class:`ContradictionGroup` — неизменяемая группа с :meth:`as_dict`.
* :func:`filter_contradictions` — отбор строк по материалу/свойству.
* :func:`group_contradictions` — группировка по паре ключей с дедупликацией.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ContradictionGroup:
    """Неизменяемая группа противоречий по материалу×свойству (§5.2.7).

    Immutable group of contradictions for one material×property pair. ``count``
    equals ``len(claim_ids)`` after order-preserving deduplication of claim ids.
    :meth:`as_dict` yields the wire form.
    """

    material: str
    property: str
    claim_ids: tuple[str, ...]
    count: int

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление группы / wire form (§5.2.7)."""
        return {
            "material": self.material,
            "property": self.property,
            "claim_ids": list(self.claim_ids),
            "count": self.count,
        }


def filter_contradictions(
    rows: Sequence[Mapping[str, Any]],
    *,
    material: str | None = None,
    property: str | None = None,
) -> list[dict[str, Any]]:
    """Отобрать строки противоречий по материалу/свойству (§5.2.7).

    Filter contradiction rows by ``material`` and/or ``property``. A ``None``
    filter matches any value for that key; both ``None`` returns every row.
    Rows are returned as plain dicts, preserving input order.

    :param rows: последовательность отображений с ключами материала/свойства.
    :param material: требуемый материал либо ``None`` / required material or None.
    :param property: требуемое свойство либо ``None`` / required property or None.
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        if material is not None and row.get("material") != material:
            continue
        if property is not None and row.get("property") != property:
            continue
        out.append(dict(row))
    return out


def group_contradictions(
    rows: Sequence[Mapping[str, Any]],
    by: tuple[str, str] = ("material", "property"),
) -> list[ContradictionGroup]:
    """Сгруппировать противоречия по паре ключей (§5.2.7).

    Group contradiction rows by the ``by`` pair (default material×property).
    ``claim_id`` values are deduplicated within a group while preserving first
    appearance order, so ``count`` reflects distinct claims. Groups are sorted
    by ``count`` descending, then by material ascending.

    :param rows: последовательность строк противоречий / contradiction rows.
    :param by: пара ключей группировки ``(material_key, property_key)``.
    """
    material_key, property_key = by
    order: list[tuple[str, str]] = []
    claims: dict[tuple[str, str], list[str]] = {}
    seen: dict[tuple[str, str], set[str]] = {}

    for row in rows:
        key = (row.get(material_key, ""), row.get(property_key, ""))
        if key not in claims:
            order.append(key)
            claims[key] = []
            seen[key] = set()
        claim_id = row.get("claim_id")
        if claim_id is not None and claim_id not in seen[key]:
            seen[key].add(claim_id)
            claims[key].append(claim_id)

    groups = [
        ContradictionGroup(
            material=key[0],
            property=key[1],
            claim_ids=tuple(claims[key]),
            count=len(claims[key]),
        )
        for key in order
    ]
    groups.sort(key=lambda g: (-g.count, g.material))
    return groups

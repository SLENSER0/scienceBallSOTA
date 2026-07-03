"""Facet aggregation for the ``GET /facets`` quick-filter lists (§14.15).

Подсчёт значений фасетов (material/property/lab/regime и числовые диапазоны)
по строкам узлов, уже загруженным в память. Ретривер отдаёт попадания как
OpenSearch DSL, но у шлюза нет собственного агрегатора фасетов — этот модуль
считает списки значений быстрых фильтров прямо из ``list[dict]``. Чистый
stdlib, без зависимостей, поэтому легко тестируется и переиспользуется.

Compute the quick-filter value lists for ``GET /facets`` (material / property /
lab / regime plus numeric ranges) from in-memory node rows. The retriever emits
hits as OpenSearch DSL, and no gateway-side facet aggregator exists, so this
module counts value lists directly from ``list[dict]``. Pure stdlib,
dependency-free.

* :class:`FacetValue` — frozen ``(value, count)`` pair with :meth:`as_dict`.
* :class:`Facet`      — frozen ``(field, values)`` bucket with :meth:`as_dict`.
* :func:`compute_facet`   — rows + field → :class:`Facet` (count, sort, truncate).
* :func:`compute_facets`  — rows + fields → ``list[Facet]``.
* :func:`numeric_range`   — rows + field → ``(min, max)`` or ``None``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FacetValue:
    """Одно значение фасета и число его вхождений (§14.15).

    A single facet bucket: the string ``value`` and how many rows carried it.
    """

    value: str
    count: int

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление значения / wire form (§14.15)."""
        return {"value": self.value, "count": self.count}


@dataclass(frozen=True, slots=True)
class Facet:
    """Фасет: имя поля и упорядоченный кортеж его значений (§14.15).

    A facet for one ``field`` with its ordered tuple of :class:`FacetValue`
    buckets (count-desc, then value-asc).
    """

    field: str
    values: tuple[FacetValue, ...]

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление фасета / wire form (§14.15)."""
        return {"field": self.field, "values": [v.as_dict() for v in self.values]}


def compute_facet(
    rows: Sequence[Mapping[str, Any]],
    field: str,
    top: int | None = None,
) -> Facet:
    """Собрать фасет для ``field`` из строк ``rows`` (§14.15).

    Считаем вхождения значений поля ``field``; строки, где ключа нет, в подсчёт
    не попадают. Результат сортируется по убыванию счётчика, при равенстве — по
    возрастанию значения (алфавитно). Если задан ``top``, кортеж усекается до
    первых ``top`` значений.

    Count occurrences of ``field`` across ``rows``; rows missing the key are
    skipped. Buckets are ordered by count descending, ties broken by value
    ascending. When ``top`` is given, the tuple is truncated to the first
    ``top`` buckets.
    """
    counts: Counter[str] = Counter()
    for row in rows:
        if field in row:
            counts[str(row[field])] += 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    if top is not None:
        ordered = ordered[:top]
    values = tuple(FacetValue(value=value, count=count) for value, count in ordered)
    return Facet(field=field, values=values)


def compute_facets(
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
) -> list[Facet]:
    """Собрать фасеты для каждого поля из ``fields`` (§14.15).

    Compute one :class:`Facet` per entry of ``fields``, preserving their order.
    """
    return [compute_facet(rows, field) for field in fields]


def numeric_range(
    rows: Sequence[Mapping[str, Any]],
    field: str,
) -> tuple[float, float] | None:
    """Найти числовой диапазон ``(min, max)`` поля ``field`` (§14.15).

    Собираем числовые значения ``field`` из строк (строки без ключа
    пропускаются) и возвращаем ``(min, max)`` как ``float``. Если ни одного
    значения нет, возвращаем ``None``.

    Collect the numeric ``field`` values across ``rows`` (rows missing the key
    are skipped) and return ``(min, max)`` as floats, or ``None`` when no value
    is present.
    """
    numbers = [float(row[field]) for row in rows if field in row]
    if not numbers:
        return None
    return (min(numbers), max(numbers))

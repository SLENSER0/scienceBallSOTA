"""Property/range/composite index selection advisor (§3.11).

Чистый советчик (*pure advisor*) над каталогом :data:`kg_schema.constraints.CONSTRAINTS`,
отвечающий на критерий приёмки §3.11 — «PROFILE использует ``NodeIndexSeek``, а не
``AllNodesScan``». Каталог декларирует, какие ``INDEX``-объекты существуют; этот модуль
отображает запрос ``(label, filter-props)`` на бэкенд-индекс, который его поддержит, и
сообщает предполагаемый метод доступа (*access method*) планировщика.

Правило выбора (§3.11): для метки берутся все ограничения вида ``ConstraintKind.INDEX``;
если ведущее свойство (*leading property*) какого-либо индекса присутствует в множестве
фильтруемых свойств запроса, планировщик может выполнить ``NodeIndexSeek`` по этому
индексу; иначе остаётся полный обход ``AllNodesScan`` без индекса.

Kuzu note: на встроенном профиле кастомные свойства узла НЕ являются запрашиваемыми
колонками (их читают через ``get_node()``); советчик остаётся декларативным описанием
намерения планировщика серверного профиля (Neo4j) и не обращается к хранилищу.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_schema.constraints import CONSTRAINTS, ConstraintKind

# Планировщиковые методы доступа (*access methods*), которыми оперирует §3.11.
SEEK: str = "NodeIndexSeek"  # индекс поддержал фильтр — точечный поиск по индексу
SCAN: str = "AllNodesScan"  # индекса нет — полный обход узлов метки


@dataclass(frozen=True)
class IndexPlan:
    """Selected backing index (or its absence) for one ``(label, filters)`` query (§3.11).

    Attributes
    ----------
    label:
        Целевая метка узла (*node label*), например ``"Measurement"``.
    filtered_props:
        Отсортированные свойства запроса-фильтра (*filter properties*), как задано вызовом.
    index_name:
        Имя поддерживающего индекса, либо ``None``, если ни один индекс не подходит.
    access:
        :data:`SEEK` (``NodeIndexSeek``) при наличии индекса, иначе :data:`SCAN`.
    covered_props:
        Свойства выбранного индекса (*covered properties*); пустой кортеж при ``SCAN``.
    """

    label: str
    filtered_props: tuple[str, ...]
    index_name: str | None
    access: str
    covered_props: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a flat, JSON-friendly dict for API / schema-view callers (§3.11)."""
        return {
            "label": self.label,
            "filtered_props": list(self.filtered_props),
            "index_name": self.index_name,
            "access": self.access,
            "covered_props": list(self.covered_props),
        }


def _label_indexes(label: str) -> tuple[Any, ...]:
    """All ``INDEX``-kind constraints for ``label``, in catalog declaration order (§3.11)."""
    return tuple(c for c in CONSTRAINTS if c.kind == ConstraintKind.INDEX and c.label == label)


def choose_index(label: str, filter_props: set[str]) -> IndexPlan:
    """Pick the backing index for a ``(label, filter_props)`` query (§3.11).

    Сканирует ``INDEX``-ограничения метки и выбирает первый (в порядке каталога), чьё
    ведущее свойство входит в ``filter_props``: тогда ``access == SEEK`` и заполняются
    ``index_name`` / ``covered_props``. Если совпадений нет — ``access == SCAN``,
    ``index_name is None`` и ``covered_props`` пуст.
    """
    filtered = tuple(sorted(filter_props))
    for c in _label_indexes(label):
        if c.properties and c.properties[0] in filter_props:
            return IndexPlan(
                label=label,
                filtered_props=filtered,
                index_name=c.name,
                access=SEEK,
                covered_props=tuple(c.properties),
            )
    return IndexPlan(
        label=label,
        filtered_props=filtered,
        index_name=None,
        access=SCAN,
        covered_props=(),
    )


def supports_seek(label: str, props: set[str]) -> bool:
    """True iff some index lets the planner seek instead of scan for ``props`` (§3.11)."""
    return choose_index(label, props).access == SEEK


def indexed_props(label: str) -> frozenset[str]:
    """Leading (seek-driving) properties of every ``INDEX`` on ``label`` (§3.11)."""
    return frozenset(c.properties[0] for c in _label_indexes(label) if c.properties)


__all__ = [
    "SCAN",
    "SEEK",
    "IndexPlan",
    "choose_index",
    "indexed_props",
    "supports_seek",
]

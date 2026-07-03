"""Ontology diff — сравнение двух версий схемы (§3.22).

Чистые (*pure*) функции без побочных эффектов: сравнивают два снимка (*snapshot*)
онтологии — множество меток узлов (:data:`~kg_schema.labels.ALL_LABELS`) и множество
сигнатур рёбер (:data:`~kg_schema.relationships.EDGE_SCHEMA`) — и отдают разницу
(*delta*) как замороженный :class:`OntologyDiff`.

Направление (*direction*): аргумент ``a`` — базовая (старая) версия, ``b`` — новая.
Поэтому ``added`` = появилось в ``b``, ``removed`` = пропало из ``a``, ``common`` —
пересечение. Диф асимметричен: ``diff(a, b).added == diff(b, a).removed`` (§3.22).

Модуль ничего не читает из графа Kuzu — работает только с декларативными каталогами
схемы (``labels.py`` / ``relationships.py``), поэтому пригоден для CI-gate дрейфа схемы.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_schema.relationships import EdgeSig


def diff_labels(a: set[str], b: set[str]) -> dict[str, frozenset[str]]:
    """Diff меток узлов между базой ``a`` и новой ``b`` (§3.22).

    ``added`` — метки только в ``b``; ``removed`` — только в ``a``; ``common`` — в обоих.
    """
    sa, sb = frozenset(a), frozenset(b)
    return {"added": sb - sa, "removed": sa - sb, "common": sa & sb}


def diff_edges(
    a: set[EdgeSig] | list[EdgeSig],
    b: set[EdgeSig] | list[EdgeSig],
) -> dict[str, frozenset[EdgeSig]]:
    """Diff сигнатур рёбер ``(from, rel, to)`` между базой ``a`` и новой ``b`` (§3.22).

    Принимает любые итерируемые сигнатуры (например срезы ``EDGE_SCHEMA``); дубликаты
    схлопываются множеством. ``added`` — рёбра только в ``b``; ``removed`` — только в ``a``.
    """
    sa, sb = frozenset(a), frozenset(b)
    return {"added": sb - sa, "removed": sa - sb, "common": sa & sb}


@dataclass(frozen=True, slots=True)
class OntologyDiff:
    """Замороженный (*frozen*) результат сравнения двух версий онтологии (§3.22).

    Собирает диф меток и рёбер в один неизменяемый снимок; :meth:`as_dict` отдаёт
    JSON-совместимое представление с детерминированной сортировкой для CI-артефактов.
    """

    added_labels: frozenset[str]
    removed_labels: frozenset[str]
    common_labels: frozenset[str]
    added_edges: frozenset[EdgeSig]
    removed_edges: frozenset[EdgeSig]
    common_edges: frozenset[EdgeSig]

    @classmethod
    def compare(
        cls,
        a_labels: set[str],
        b_labels: set[str],
        a_edges: set[EdgeSig] | list[EdgeSig],
        b_edges: set[EdgeSig] | list[EdgeSig],
    ) -> OntologyDiff:
        """Build a diff from base (``a_*``) and new (``b_*``) label/edge sets (§3.22)."""
        lbl = diff_labels(a_labels, b_labels)
        edg = diff_edges(a_edges, b_edges)
        return cls(
            added_labels=lbl["added"],
            removed_labels=lbl["removed"],
            common_labels=lbl["common"],
            added_edges=edg["added"],
            removed_edges=edg["removed"],
            common_edges=edg["common"],
        )

    @property
    def changed(self) -> bool:
        """True iff any label or edge was added or removed (§3.22)."""
        return bool(
            self.added_labels or self.removed_labels or self.added_edges or self.removed_edges
        )

    def as_dict(self) -> dict[str, list[Any]]:
        """Deterministic, JSON-friendly view (sorted labels + edge triples) (§3.22)."""
        return {
            "added_labels": sorted(self.added_labels),
            "removed_labels": sorted(self.removed_labels),
            "common_labels": sorted(self.common_labels),
            "added_edges": sorted(list(e) for e in self.added_edges),
            "removed_edges": sorted(list(e) for e in self.removed_edges),
            "common_edges": sorted(list(e) for e in self.common_edges),
        }

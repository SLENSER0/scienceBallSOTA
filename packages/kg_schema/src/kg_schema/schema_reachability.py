"""Declared-schema reachability lint (§8.2) — чистый статический анализ схемы.

Pure-python static analysis over :data:`kg_schema.relationships.EDGE_SCHEMA`.
Виртуальная метка ``Entity`` разворачивается в :data:`ENTITY_LABELS`; строится
направленный граф меток (только конкретные :class:`NodeLabel`), после чего
считаются достижимость от корня и «запахи» дизайна схемы (source/sink).

Никакого стора: анализ идёт только по объявленным сигнатурам рёбер (§3.5).
Рёбра в :class:`RunLabel` (``ExtractorRun`` / ``GapScanRun``) в разбиение
достижимости не входят — оно покрывает ровно множество :class:`NodeLabel`.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from kg_schema.labels import ENTITY_LABELS, NodeLabel
from kg_schema.relationships import EDGE_SCHEMA, ENTITY

# Concrete node labels — the universe of the reachability partition (§8.1).
NODE_LABELS: frozenset[str] = frozenset(str(label) for label in NodeLabel)
_ENTITY_EXPANSION: frozenset[str] = frozenset(str(label) for label in ENTITY_LABELS)


def _expand(label: str) -> frozenset[str]:
    """Развернуть виртуальную метку ``Entity`` в конкретные :data:`ENTITY_LABELS`."""
    if label == ENTITY:
        return _ENTITY_EXPANSION
    return frozenset({str(label)})


def _adjacency() -> dict[str, set[str]]:
    """Построить список смежности графа меток (только конкретные NodeLabel).

    ``Entity`` разворачивается в оба конца ребра; цели вне :data:`NODE_LABELS`
    (напр. :class:`RunLabel`) отбрасываются — граф замкнут на NodeLabel.
    """
    adj: dict[str, set[str]] = {label: set() for label in NODE_LABELS}
    for from_label, _rel, to_label in EDGE_SCHEMA:
        for src in _expand(str(from_label)):
            if src not in NODE_LABELS:
                continue
            for dst in _expand(str(to_label)):
                if dst in NODE_LABELS:
                    adj[src].add(dst)
    return adj


def _from_labels() -> frozenset[str]:
    """Все конкретные метки, встречающиеся как *from* в :data:`EDGE_SCHEMA`."""
    result: set[str] = set()
    for from_label, _rel, _to_label in EDGE_SCHEMA:
        result |= {src for src in _expand(str(from_label)) if src in NODE_LABELS}
    return frozenset(result)


def _to_labels() -> frozenset[str]:
    """Все конкретные метки, встречающиеся как *to* в :data:`EDGE_SCHEMA`."""
    result: set[str] = set()
    for _from_label, _rel, to_label in EDGE_SCHEMA:
        result |= {dst for dst in _expand(str(to_label)) if dst in NODE_LABELS}
    return frozenset(result)


@dataclass(frozen=True, slots=True)
class ReachabilityReport:
    """Отчёт о достижимости меток от корня + «запахи» схемы (§8.2).

    Attributes:
        root: корневая метка обхода.
        reachable: метки, достижимые из ``root`` по объявленным рёбрам (вкл. root).
        unreachable: ``NODE_LABELS`` минус ``reachable`` (дизъюнктны, в сумме — всё).
        sink_labels: метки без исходящих объявленных рёбер (нет строки *from*).
        source_labels: метки без входящих объявленных рёбер (нет строки *to*).
    """

    root: str
    reachable: frozenset[str]
    unreachable: frozenset[str]
    sink_labels: frozenset[str]
    source_labels: frozenset[str]

    def as_dict(self) -> dict[str, object]:
        """Сериализуемое представление; множества — как отсортированные списки."""
        return {
            "root": self.root,
            "reachable": sorted(self.reachable),
            "unreachable": sorted(self.unreachable),
            "sink_labels": sorted(self.sink_labels),
            "source_labels": sorted(self.source_labels),
        }


def reachable_labels(root: str) -> frozenset[str]:
    """BFS-достижимость меток от ``root`` по объявленным рёбрам (root включён).

    Raises:
        ValueError: если ``root`` не является известной :class:`NodeLabel`.
    """
    if root not in NODE_LABELS:
        raise ValueError(f"unknown root label: {root!r}")
    adj = _adjacency()
    seen: set[str] = {root}
    queue: deque[str] = deque([root])
    while queue:
        current = queue.popleft()
        for neighbour in adj[current]:
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    return frozenset(seen)


def reachability_report(root: str = "Document") -> ReachabilityReport:
    """Полный отчёт достижимости + source/sink «запахи» от корня ``root``.

    Raises:
        ValueError: если ``root`` не является известной :class:`NodeLabel`.
    """
    reachable = reachable_labels(root)
    unreachable = NODE_LABELS - reachable
    sink_labels = NODE_LABELS - _from_labels()
    source_labels = NODE_LABELS - _to_labels()
    return ReachabilityReport(
        root=root,
        reachable=reachable,
        unreachable=unreachable,
        sink_labels=sink_labels,
        source_labels=source_labels,
    )

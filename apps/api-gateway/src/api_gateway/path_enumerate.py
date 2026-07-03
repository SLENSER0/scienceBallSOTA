"""Перечисление простых путей для ``POST /graph/path`` (§14.6).

Эндпоинт §14.6 должен отдавать несколько путей между узлами, однако
:mod:`api_gateway.graph` возвращает лишь один кратчайший BFS-путь. Модуль на
чистом stdlib выполняет DFS-перебор всех простых (без повторов узлов) путей от
источника к цели с ограничением по числу рёбер, опционально фильтруя рёбра по
их ``type``. Результат — неизменяемый :class:`PathResult` с :meth:`as_dict`.

The §14.6 ``POST /graph/path`` endpoint should surface multiple paths, but
:mod:`api_gateway.graph` only returns a single shortest BFS path. Pure stdlib —
DFS-enumerates every simple (no repeated node) path from ``source`` to
``target`` with a hop-count cap, optionally restricted to given edge ``type``
values. Yields a frozen :class:`PathResult` with :meth:`as_dict`.

* :class:`PathResult` — неизменяемый набор путей с флагом усечения.
* :func:`enumerate_paths` — DFS-перебор простых путей от источника к цели.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PathResult:
    """Неизменяемый результат перебора простых путей (§14.6).

    Immutable result of simple-path enumeration. ``paths`` holds node-id tuples
    ordered source→target; ``count`` equals ``len(paths)``; ``truncated`` is
    ``True`` when the ``max_paths`` cap was reached. :meth:`as_dict` yields the
    wire form.
    """

    paths: tuple[tuple[str, ...], ...]
    count: int
    truncated: bool

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление результата / wire form (§14.6)."""
        return {
            "paths": [list(path) for path in self.paths],
            "count": self.count,
            "truncated": self.truncated,
        }


def _build_adjacency(
    edges: Sequence[Mapping[str, Any]],
    edge_types: set[str] | None,
) -> dict[str, list[str]]:
    """Построить список смежности из рёбер / build adjacency (§14.6).

    Каждое ребро — отображение с ключами ``source``/``target`` и опциональным
    ``type``. Если задан ``edge_types``, рёбра с иным ``type`` пропускаются.
    """
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        if edge_types is not None and edge.get("type") not in edge_types:
            continue
        src = edge["source"]
        dst = edge["target"]
        adjacency.setdefault(src, []).append(dst)
    return adjacency


def enumerate_paths(
    edges: Sequence[Mapping[str, Any]],
    source: str,
    target: str,
    *,
    max_length: int = 4,
    max_paths: int = 50,
    edge_types: set[str] | None = None,
) -> PathResult:
    """DFS-перебор простых путей от ``source`` к ``target`` (§14.6).

    Возвращает все простые пути (без повторного посещения узла) с числом рёбер
    ``<= max_length``. При заданном ``edge_types`` учитываются только рёбра с
    подходящим ``type``. Перебор прекращается при достижении ``max_paths`` — тогда
    :attr:`PathResult.truncated` истинно.

    DFS-enumerates every simple path (no node revisited) from ``source`` to
    ``target`` whose hop count is ``<= max_length``. When ``edge_types`` is set,
    only edges with a matching ``type`` are traversed. Enumeration stops once
    ``max_paths`` paths are collected, in which case ``truncated`` is ``True``.
    """
    adjacency = _build_adjacency(edges, edge_types)
    found: list[tuple[str, ...]] = []
    truncated = False

    if max_length < 0 or max_paths <= 0:
        return PathResult(paths=(), count=0, truncated=False)

    # Итеративный DFS: стек кадров (текущий узел, путь, множество посещённых).
    # Iterative DFS over frames of (node, path, visited-set).
    stack: list[tuple[str, tuple[str, ...], frozenset[str]]] = [
        (source, (source,), frozenset({source}))
    ]
    while stack:
        node, path, visited = stack.pop()
        if node == target and len(path) > 1:
            found.append(path)
            if len(found) >= max_paths:
                # Кап достигнут: помечаем усечение, если остались варианты.
                truncated = bool(stack)
                break
            continue
        if len(path) - 1 >= max_length:
            continue
        for neighbour in adjacency.get(node, ()):
            if neighbour in visited:
                continue  # простые пути: узел не повторяется / no revisits
            stack.append((neighbour, (*path, neighbour), visited | {neighbour}))

    return PathResult(paths=tuple(found), count=len(found), truncated=truncated)

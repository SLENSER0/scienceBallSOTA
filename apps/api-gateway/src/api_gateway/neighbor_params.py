"""Entity-neighbor / graph-expand parameter parsing (§14.5/§14.6).

Разбор параметров запроса соседей узла и раскрытия подграфа: список идентификаторов
узлов, глубина обхода (с зажимом в допустимый диапазон) и фильтры по типам узлов и
рёбер. Списки задаются через запятую, дедуплицируются с сохранением порядка, а
глубина ограничивается ``[DEFAULT_DEPTH..MAX_DEPTH]``. Модуль — на чистом stdlib.

Parse the entity-neighbors / subgraph-expand query parameters: a list of node ids,
a traversal depth (clamped into range) and node-/edge-type filters. Lists are given
as comma-separated values, de-duplicated with order preserved, and the depth is
clamped into ``[DEFAULT_DEPTH..MAX_DEPTH]``. Pure stdlib, dependency-free.

* :class:`NeighborParams` — frozen params bundle with :meth:`as_dict`.
* :func:`clamp_depth`     — raw depth → clamped ``int`` in range.
* :func:`parse_neighbor_params` — request mapping → :class:`NeighborParams`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

#: Глубина обхода по умолчанию / default traversal depth.
DEFAULT_DEPTH = 1

#: Максимально допустимая глубина обхода / maximum allowed traversal depth.
MAX_DEPTH = 3


@dataclass(frozen=True, slots=True)
class NeighborParams:
    """Неизменяемый набор параметров соседей/раскрытия подграфа (§14.5/§14.6).

    Immutable bundle of neighbor/expand parameters. ``node_ids`` are the seed
    nodes; ``depth`` is already clamped into ``[DEFAULT_DEPTH..MAX_DEPTH]``;
    ``node_types``/``edge_types`` are de-duplicated, order-preserving filters.
    """

    node_ids: tuple[str, ...]
    depth: int
    node_types: tuple[str, ...]
    edge_types: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление параметров / wire form (§14.5/§14.6)."""
        return {
            "node_ids": list(self.node_ids),
            "depth": self.depth,
            "node_types": list(self.node_types),
            "edge_types": list(self.edge_types),
        }


def clamp_depth(raw: int | None) -> int:
    """Зажать глубину обхода в диапазон ``[DEFAULT_DEPTH..MAX_DEPTH]`` (§14.6).

    ``None`` → :data:`DEFAULT_DEPTH`; значения ниже ``DEFAULT_DEPTH`` поднимаются
    до него, значения выше :data:`MAX_DEPTH` опускаются до него.

    ``None`` maps to :data:`DEFAULT_DEPTH`; values below ``DEFAULT_DEPTH`` are
    raised to it and values above :data:`MAX_DEPTH` are lowered to it.
    """
    if raw is None:
        return DEFAULT_DEPTH
    if raw < DEFAULT_DEPTH:
        return DEFAULT_DEPTH
    if raw > MAX_DEPTH:
        return MAX_DEPTH
    return raw


def _split_csv(value: Any) -> tuple[str, ...]:
    """Разбить CSV-строку в кортеж с дедупликацией по порядку / ordered dedupe.

    Пустые токены отбрасываются; порядок первого появления сохраняется.
    Empty tokens are dropped; first-occurrence order is preserved.
    """
    if value is None:
        return ()
    seen: dict[str, None] = {}
    for token in str(value).split(","):
        item = token.strip()
        if item and item not in seen:
            seen[item] = None
    return tuple(seen)


def parse_neighbor_params(params: Mapping[str, Any]) -> NeighborParams:
    """Разобрать mapping запроса в :class:`NeighborParams` (§14.5/§14.6).

    Читает ключи ``node_ids``, ``types`` (→ ``node_types``) и ``edge_types`` как
    CSV-списки (дедуплицированы, порядок сохранён) и ``depth`` (зажат в диапазон).
    Отсутствующий или пустой ``depth`` даёт :data:`DEFAULT_DEPTH`; нечисловые
    значения глубины также трактуются как отсутствующие.

    Reads ``node_ids``, ``types`` (→ ``node_types``) and ``edge_types`` as CSV
    lists (de-duplicated, order preserved) and ``depth`` (clamped). A missing or
    empty ``depth`` yields :data:`DEFAULT_DEPTH`; non-numeric depth values are
    likewise treated as absent.
    """
    raw_depth = params.get("depth")
    depth_value: int | None
    if raw_depth is None or (isinstance(raw_depth, str) and not raw_depth.strip()):
        depth_value = None
    else:
        try:
            depth_value = int(raw_depth)
        except (TypeError, ValueError):
            depth_value = None
    return NeighborParams(
        node_ids=_split_csv(params.get("node_ids")),
        depth=clamp_depth(depth_value),
        node_types=_split_csv(params.get("types")),
        edge_types=_split_csv(params.get("edge_types")),
    )

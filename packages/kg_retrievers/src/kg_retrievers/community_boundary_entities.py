"""§11.6 community boundary / bridge entity detection.

Обнаружение сущностей на границах сообществ / community-boundary entity detection.
Boundary entity — узел, у которого есть рёбра, уходящие в *другое* сообщество
Leiden-разбиения. В отличие от :mod:`kg_retrievers.graph_cut_points`, который ищет
глобальные точки сочленения (articulation points), игнорируя сообщества, здесь всё
считается относительно membership-карты: важна не глобальная связность, а то,
сколько разных чужих сообществ «трогает» узел.

Unlike ``graph_cut_points`` (global articulation points, community-agnostic), this
module keys everything on the Leiden ``membership`` map. A node is a *bridge* to the
degree that its edges cross community lines: ``bridge_score`` counts the *distinct*
external communities it reaches, ``external_degree`` counts the crossing edges, and
``internal_degree`` counts edges that stay inside the home community.

Pure python — no store/graph/DB access: на вход уже собранные рёбра и membership.
Kuzu note: custom node props are NOT queryable columns — ``community_id`` кладётся
в membership заранее (RETURN base columns, остальное через ``get_node``), а здесь
читается прямо из переданных структур.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BoundaryEntity:
    """Сущность на границе сообщества (§11.6). One community-boundary entity.

    ``entity_id`` — идентификатор узла; ``home_community`` — его сообщество из
    membership; ``external_communities`` — отсортированный кортеж *различных* чужих
    сообществ, куда уходят рёбра; ``external_degree`` — число рёбер, пересекающих
    границу; ``internal_degree`` — число рёбер внутри home_community;
    ``bridge_score`` — ``len(external_communities)`` (сколько разных чужих сообществ
    затронуто).
    """

    entity_id: str
    home_community: int
    external_communities: tuple[int, ...]
    external_degree: int
    internal_degree: int
    bridge_score: int

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready projection; ``bridge_score`` == number of external communities."""
        return {
            "entity_id": self.entity_id,
            "home_community": self.home_community,
            "external_communities": list(self.external_communities),
            "external_degree": self.external_degree,
            "internal_degree": self.internal_degree,
            "bridge_score": self.bridge_score,
        }


def _undirected_neighbours(
    edges: Iterable[tuple[str, str]],
    membership: Mapping[str, int],
) -> dict[str, list[str]]:
    """Build an undirected multi-adjacency, keeping only nodes present in membership.

    Рёбра неориентированные, кратность сохраняется (для степеней), self-loops
    отбрасываются. Endpoints без записи в membership игнорируются целиком.
    """
    adj: dict[str, list[str]] = {}
    for src, dst in edges:
        if src == dst:
            continue  # self-loops contribute to neither internal nor external degree
        if src not in membership or dst not in membership:
            continue  # unknown community -> cannot classify the crossing
        adj.setdefault(src, []).append(dst)
        adj.setdefault(dst, []).append(src)
    return adj


def find_boundary_entities(
    edges: Iterable[tuple[str, str]],
    membership: Mapping[str, int],
) -> list[BoundaryEntity]:
    """Return entities with at least one edge crossing into another community (§11.6).

    Сортировка: ``bridge_score`` убыв., затем ``external_degree`` убыв., затем
    ``entity_id`` возр. Возвращаются только узлы с ``external_degree > 0``.
    Sorted by bridge_score desc, external_degree desc, entity_id asc; only entities
    that actually reach a foreign community are included.
    """
    adj = _undirected_neighbours(edges, membership)
    result: list[BoundaryEntity] = []
    for entity_id, neighbours in adj.items():
        home = membership[entity_id]
        external_degree = 0
        internal_degree = 0
        external_set: set[int] = set()
        for other in neighbours:
            other_community = membership[other]
            if other_community == home:
                internal_degree += 1
            else:
                external_degree += 1
                external_set.add(other_community)
        if external_degree == 0:
            continue  # interior node — every edge stays inside the home community
        external_communities = tuple(sorted(external_set))
        result.append(
            BoundaryEntity(
                entity_id=entity_id,
                home_community=home,
                external_communities=external_communities,
                external_degree=external_degree,
                internal_degree=internal_degree,
                bridge_score=len(external_communities),
            )
        )
    result.sort(key=lambda b: (-b.bridge_score, -b.external_degree, b.entity_id))
    return result


def top_bridges(
    edges: Iterable[tuple[str, str]],
    membership: Mapping[str, int],
    k: int,
) -> list[str]:
    """Return the ``entity_id`` of the top-``k`` boundary entities (§11.6).

    Порядок совпадает с :func:`find_boundary_entities`; при ``k <= 0`` — пустой
    список. Order matches ``find_boundary_entities``; ``k <= 0`` yields ``[]``.
    """
    if k <= 0:
        return []
    return [b.entity_id for b in find_boundary_entities(edges, membership)[:k]]

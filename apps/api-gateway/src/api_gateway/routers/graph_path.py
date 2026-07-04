"""Path search Material↔Property с подсветкой найденного пути (§17.8, §5.2.3, §14.6).

«Через ЧТО материал связан со свойством?» — endpoint принимает две сущности
(обычно Material → Property) и возвращает *реляционные пути* между ними плюс
подграф, в котором узлы и рёбра лучшего пути помечены визуальным флагом
``onPath`` для подсветки в Graph Explorer (§17.8 «path search → highlight found
path»).

Модуль — тонкий REST-слой над уже готовыми чистыми функциями:

* :func:`api_gateway.path_enumerate.enumerate_paths` — DFS-перебор простых путей
  ``source→target`` длиной ≤ ``max_hops`` (§14.6). Граф горного дела ненаправлен
  по смыслу («материал ↔ свойство»), поэтому каждое хранимое ребро подаётся в
  перечислитель в обе стороны — обход становится ненаправленным, как в BFS
  ``GET /graph/path``.
* :func:`kg_retrievers.graph_path_highlight.highlight_path` /
  :func:`~kg_retrievers.graph_path_highlight.path_highlight_summary` — наносят
  найденный путь на ``GraphResponse`` (§5.3): ``onPath``/``pathOrder`` на узлах,
  ``onPath`` на рёбрах пути; сводка по рёбрам и разрывам.

Работает на любом рантайм-профиле: variable-length паттерн ``-[:Rel*1..N]-`` и
``store.edges_among`` / ``store.subgraph_from_ids`` одинаковы для Neo4j
(server-профиль :8000) и Kuzu (embedded) — никакого Neo4j-специфичного
``shortestPath``. Отдельный префикс ``/graph-path`` не конфликтует с
``GET /api/v1/graph/path`` (одиночный BFS-путь) из :mod:`api_gateway.routers.graph`.
"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api_gateway.deps import get_store
from api_gateway.path_enumerate import enumerate_paths
from kg_retrievers.graph_path_highlight import highlight_path, path_highlight_summary

router = APIRouter(prefix="/api/v1/graph-path", tags=["graph-path"])

# Надёжность ребра по умолчанию, когда ``confidence`` не задан (как в PathRAG §12.5).
_DEFAULT_WEIGHT = 0.8
# Верхняя граница региона обхода — сколько узлов вокруг источника рассматривать.
_REGION_LIMIT = 800


def _node_brief(store: Any, node_id: str) -> dict[str, Any] | None:
    """Короткая карточка узла ``{id, name, type}`` для пикеров и заголовков."""
    nd = store.get_node(node_id)
    if nd is None:
        return None
    return {
        "id": nd["id"],
        "name": nd.get("name") or nd.get("canonical_name") or nd["id"],
        "type": nd.get("label", "Entity"),
    }


def _reachable_ids(store: Any, source: str, max_hops: int) -> set[str]:
    """Множество id, достижимых из ``source`` за ≤ ``max_hops`` рёбер (ненаправленно).

    Регион ограничивает перебор простых путей: любой простой путь длиной
    ≤ ``max_hops`` от ``source`` целиком лежит в этом регионе, поэтому его
    достаточно, чтобы найти все пути до ``target``.
    """
    hops = max(1, min(int(max_hops), 6))
    rows = store.rows(
        f"MATCH (a:Node {{id:$id}})-[:Rel*1..{hops}]-(b:Node) "
        f"RETURN DISTINCT b.id LIMIT {_REGION_LIMIT}",
        {"id": source},
    )
    ids = {r[0] for r in rows}
    ids.add(source)
    return ids


@router.get("/endpoints")
def endpoints(
    label: str = Query("Material", description="метка узлов для пикера (Material/Property/…)"),
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    """Узлы заданной метки для выбора источника/цели пути (§17.8 UI выбора)."""
    store = get_store()
    rows = store.rows(
        "MATCH (n:Node) WHERE n.label = $lab AND n.name IS NOT NULL "
        f"RETURN n.id, n.name ORDER BY n.name LIMIT {int(limit)}",
        {"lab": label},
    )
    return {
        "label": label,
        "count": len(rows),
        "nodes": [{"id": r[0], "name": r[1], "type": label} for r in rows],
    }


class PathSearchRequest(BaseModel):
    """Запрос поиска путей между двумя сущностями (§17.8)."""

    source: str = Field(..., description="id узла-источника (обычно Material)")
    target: str = Field(..., description="id узла-цели (обычно Property)")
    max_hops: int = Field(4, ge=1, le=6, description="макс. число рёбер в пути")
    top_n: int = Field(6, ge=1, le=25, description="сколько лучших путей вернуть")
    edge_types: list[str] | None = Field(
        None, description="ограничить обход рёбрами этих RelType (напр. IMPROVES)"
    )


def _path_reliability(path: tuple[str, ...], conf: dict[tuple[str, str], float]) -> float:
    """Потоковая надёжность пути — произведение весов рёбер (флоат в [0, 1])."""
    score = 1.0
    for a, b in pairwise(path):
        score *= conf.get((a, b), _DEFAULT_WEIGHT)
    return score


def _describe_path(
    path: tuple[str, ...],
    graph: dict[str, Any],
    name_by_id: dict[str, str],
    type_by_edge: dict[str, str],
    reliability: float,
) -> dict[str, Any]:
    """Собрать читаемое описание пути: имена узлов, типы рёбер, линеаризация."""
    summary = path_highlight_summary(graph, path)
    rel_types = [type_by_edge.get(eid, "REL") for eid in summary.edge_ids]
    node_names = [name_by_id.get(nid, nid) for nid in path]

    parts: list[str] = [node_names[0]] if node_names else []
    for name, rel in zip(node_names[1:], rel_types, strict=False):
        parts.append(f"-[{rel}]->")
        parts.append(name)

    return {
        "nodeIds": list(path),
        "nodeNames": node_names,
        "edgeIds": list(summary.edge_ids),
        "relTypes": rel_types,
        "length": summary.length,
        "reliability": round(reliability, 4),
        "linear": " ".join(parts),
        "complete": not summary.missing_segments,
    }


@router.post("/search")
def search(req: PathSearchRequest) -> dict:
    """Найти пути ``source → target`` и подсветить лучший в подграфе (§17.8).

    Возвращает: карточки источника/цели, ранжированный список путей
    (кратчайшие и наиболее надёжные первыми) и ``graph`` — ``GraphResponse``
    объединения всех путей, где узлы/рёбра *лучшего* пути помечены ``onPath``
    для подсветки в Graph Explorer.
    """
    store = get_store()
    src = _node_brief(store, req.source)
    dst = _node_brief(store, req.target)
    if src is None or dst is None:
        raise HTTPException(status_code=404, detail="source or target node not found")

    empty = {
        "found": False,
        "source": src,
        "target": dst,
        "maxHops": req.max_hops,
        "count": 0,
        "paths": [],
        "graph": {"nodes": [], "edges": []},
        "best": None,
    }
    if req.source == req.target:
        return {**empty, "detail": "source and target coincide"}

    # 1. Регион обхода вокруг источника + рёбра внутри него.
    region = _reachable_ids(store, req.source, req.max_hops)
    if req.target not in region:
        return {**empty, "detail": "target unreachable within max_hops"}

    region_edges = store.edges_among(region)
    undirected: list[dict[str, Any]] = []
    conf: dict[tuple[str, str], float] = {}
    for e in region_edges:
        w = e.confidence if e.confidence is not None else _DEFAULT_WEIGHT
        undirected.append({"source": e.source, "target": e.target, "type": e.type})
        undirected.append({"source": e.target, "target": e.source, "type": e.type})
        conf[(e.source, e.target)] = w
        conf[(e.target, e.source)] = w

    # 2. Перебор простых путей (ненаправленно, обе стороны каждого ребра поданы).
    edge_types = set(req.edge_types) if req.edge_types else None
    result = enumerate_paths(
        undirected,
        req.source,
        req.target,
        max_length=req.max_hops,
        max_paths=max(req.top_n * 6, 60),
        edge_types=edge_types,
    )
    if result.count == 0:
        return {**empty, "detail": "no path found"}

    # 3. Ранжирование: короче → надёжнее → лексикографически (детерминизм).
    ranked = sorted(
        result.paths,
        key=lambda p: (len(p) - 1, -_path_reliability(p, conf), p),
    )[: req.top_n]

    # 4. Подграф объединения путей + подсветка лучшего пути.
    union: set[str] = set()
    for p in ranked:
        union.update(p)
    base = store.subgraph_from_ids(list(union), expand=0).model_dump(by_alias=True)

    name_by_id = {n["id"]: n.get("label") or n["id"] for n in base.get("nodes", [])}
    type_by_edge = {
        e["id"]: e.get("type") or e.get("label") or "REL" for e in base.get("edges", [])
    }

    best_path = ranked[0]
    highlighted = highlight_path(base, best_path)
    best_summary = path_highlight_summary(base, best_path)

    paths = [
        _describe_path(p, base, name_by_id, type_by_edge, _path_reliability(p, conf))
        for p in ranked
    ]

    return {
        "found": True,
        "source": src,
        "target": dst,
        "maxHops": req.max_hops,
        "count": len(paths),
        "truncated": result.truncated,
        "paths": paths,
        "graph": highlighted,
        "best": best_summary.as_dict(),
    }

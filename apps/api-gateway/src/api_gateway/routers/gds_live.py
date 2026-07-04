"""Живой Neo4j GDS: Louvain-сообщества + nodeSimilarity на боевой БД (§3.14).

Раскрашиваем 66k-узловой клубок в цвета сообществ прямо на живом графе. До сих
пор GDS жил только в embedded-модулях (`kg_retrievers.community`,
`kg_retrievers.graph_algos` — NetworkX-проекция Kuzu, §12.8): ни одного
``CALL gds`` на реальном Neo4j. Этот роутер закрывает пробел — он гоняет
настоящие GDS-процедуры (`gds.graph.project`, `gds.louvain.write`,
`gds.nodeSimilarity.stream`) на server-профиле и отдаёт результат так, чтобы 3D-
клубок (``ForceGraph3D``) окрасил узлы по ``community_id``, а панель показала
«похожие материалы».

Дизайн:
- работает ТОЛЬКО на server-профиле (Neo4j + GDS-плагин, §3.9). На embedded
  (Kuzu) GDS-плагина нет — тогда все ручки честно отвечают ``available: false``
  и подсказывают запустить embedded-эквивалент ``/api/v1/graph-communities``;
- проекция ``:Node``/``:Rel`` (UNDIRECTED) в именованный in-memory граф
  ``sb_live_gds`` — идемпотентно (drop-if-exists), с гарантированной очисткой
  in-memory графа после расчёта (критерий §3.14: ``gds.graph.list`` пуст);
- каждый job логируется под ``run_id`` (provenance §3.7);
- Louvain пишет ``community_id`` обратно на узлы — тот же property, что читает
  embedded-путь и ``node_to_dto``/``GraphNode.communityId``, поэтому канвас 2D/3D
  уже умеет его подхватывать.

Роутер только читает GDS/пишет ``community_id`` — рёбер не создаёт. Отдельный
префикс ``/gds-live`` не конфликтует с ``/graph`` и ``/graph-communities``.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_gateway.deps import get_store
from kg_common import GraphResponse, get_logger, get_settings, make_id

router = APIRouter(prefix="/api/v1/gds-live", tags=["gds-live"])

_log = get_logger("api.gds_live")

# Префикс in-memory GDS-проекции. Каждый запрос получает УНИКАЛЬНОЕ имя
# ``sb_live_gds_<uuid>`` (H-9): фиксированное имя + drop-then-project без блокировки
# приводило к тому, что конкурентные запросы затирали проекцию друг друга (пустые/
# неверные результаты, ошибки «graph does not exist»). Уникальное имя изолирует job,
# а гарантированный drop в finally не даёт in-memory графам утекать.
_GRAPH_PREFIX = "sb_live_gds"
# Property, куда Louvain пишет метку сообщества (тот же, что читает node_to_dto).
_COMM_PROP = "community_id"


def _is_server() -> bool:
    """True, если активен server-профиль (Neo4j + GDS-плагин доступны)."""
    return get_settings().runtime_profile == "server"


def _gds(store: Any, cypher: str, params: dict | None = None) -> list[list[Any]]:
    """Прогнать GDS/Cypher на живом Neo4j, обернув отсутствие плагина в 503.

    ``store.rows`` открывает ``driver.session()`` и возвращает ``record.values()``.
    Если GDS-плагин не установлен, Neo4j бросает ``ClientError`` про неизвестную
    процедуру — переводим в понятный 503, а не 500.
    """
    try:
        return store.rows(cypher, params or {})
    except Exception as exc:
        msg = str(exc)
        _log.warning("gds_live.cypher_failed", error=msg[:300])
        if "gds." in msg and ("no procedure" in msg.lower() or "unknown" in msg.lower()):
            raise HTTPException(
                status_code=503,
                detail=(
                    "GDS-плагин недоступен на Neo4j — проверьте "
                    "NEO4J_PLUGINS=graph-data-science (§3.9)"
                ),
            ) from exc
        raise HTTPException(status_code=500, detail=f"GDS call failed: {msg[:200]}") from exc


def _new_graph_name() -> str:
    """Уникальное имя проекции на один job — чтобы конкурентные запросы не пересекались (H-9)."""
    return f"{_GRAPH_PREFIX}_{uuid.uuid4().hex}"


def _live_projections(store: Any) -> int:
    """Сколько наших in-memory проекций сейчас живо (все с префиксом ``sb_live_gds``)."""
    rows = _gds(
        store,
        "CALL gds.graph.list() YIELD graphName "
        "WITH graphName WHERE graphName STARTS WITH $p "
        "RETURN count(*) AS c",
        {"p": _GRAPH_PREFIX},
    )
    return int(rows[0][0]) if rows and rows[0] else 0


def _drop_projection(store: Any, graph: str) -> None:
    """Освободить in-memory граф (критерий §3.14: список проекций пуст после job)."""
    _gds(
        store,
        "CALL gds.graph.exists($g) YIELD exists "
        "WITH exists WHERE exists "
        "CALL gds.graph.drop($g, false) YIELD graphName RETURN graphName",
        {"g": graph},
    )


def _project(store: Any) -> dict[str, Any]:
    """Спроецировать ``:Node``/``:Rel`` в UNDIRECTED in-memory граф с уникальным именем.

    Имя проекции уникально на запрос (``sb_live_gds_<uuid>``), поэтому drop-if-exists
    больше не нужен — коллизия имени исключена, а конкурентные job'ы изолированы (H-9).
    Возвращает имя проекции и её статистику (кол-во узлов/рёбер); вызывающий обязан
    сделать ``_drop_projection(store, proj["name"])`` в ``finally``.
    """
    graph = _new_graph_name()
    rows = _gds(
        store,
        "CALL gds.graph.project($g, 'Node', "
        "{Rel: {orientation: 'UNDIRECTED'}}) "
        "YIELD nodeCount, relationshipCount "
        "RETURN nodeCount, relationshipCount",
        {"g": graph},
    )
    n, r = (rows[0][0], rows[0][1]) if rows else (0, 0)
    return {"name": graph, "nodes": int(n), "relationships": int(r)}


def _require_server() -> Any:
    """Вернуть store на server-профиле, иначе 409 с подсказкой на embedded-путь."""
    if not _is_server():
        raise HTTPException(
            status_code=409,
            detail=(
                "Живой GDS доступен только на server-профиле (Neo4j). На embedded "
                "используйте /api/v1/graph-communities (NetworkX, §11)."
            ),
        )
    return get_store()


def _community_rows(store: Any) -> list[list[Any]]:
    """Прочитать (community_id, size) по узлам с меткой сообщества, крупные первыми."""
    return _gds(
        store,
        f"MATCH (n:Node) WHERE n.{_COMM_PROP} IS NOT NULL "
        f"RETURN n.{_COMM_PROP} AS c, count(*) AS size ORDER BY size DESC",
    )


def _top_entities(store: Any, community_id: int, limit: int = 6) -> list[str]:
    rows = _gds(
        store,
        f"MATCH (n:Node) WHERE n.{_COMM_PROP} = $c AND n.name IS NOT NULL "
        "RETURN n.name AS name "
        "ORDER BY coalesce(n.evidence_count, 0) DESC, n.name "
        f"LIMIT {int(limit)}",
        {"c": community_id},
    )
    return [str(r[0]) for r in rows]


@router.get("/status")
def status() -> dict:
    """Доступность живого GDS и наличие уже посчитанных сообществ.

    Дешёвая ручка для фронта: показать баннер «запустите Louvain» или уже
    раскрасить клубок. На embedded возвращает ``available: false``.
    """
    if not _is_server():
        return {
            "available": False,
            "profile": get_settings().runtime_profile,
            "reason": "GDS-плагин есть только на server-профиле (Neo4j).",
            "communities": 0,
            "clustered": False,
        }
    store = get_store()
    rows = _community_rows(store)
    return {
        "available": True,
        "profile": "server",
        "clustered": bool(rows),
        "communities": len(rows),
        "projection_live": _live_projections(store) > 0,
    }


@router.post("/louvain")
def louvain(
    min_size: int = Query(default=1, ge=1, le=100, description="минимальный размер сообщества"),
    top_communities: int = Query(default=24, ge=1, le=200),
) -> dict:
    """Запустить живой Louvain на Neo4j GDS и записать ``community_id`` на узлы (§3.14).

    Полный цикл одного job: project → ``gds.louvain.write`` → drop-проекции.
    Возвращает run-id (provenance §3.7), модулярность, число сообществ и топ-
    кластеры (размер + представительные сущности) для легенды раскраски.
    """
    store = _require_server()
    run_id = make_id("Finding", "gds-louvain-live")
    proj = _project(store)
    try:
        rows = _gds(
            store,
            "CALL gds.louvain.write($g, {writeProperty: $p}) "
            "YIELD communityCount, modularity, nodePropertiesWritten, ranLevels "
            "RETURN communityCount, modularity, nodePropertiesWritten, ranLevels",
            {"g": proj["name"], "p": _COMM_PROP},
        )
    finally:
        _drop_projection(store, proj["name"])  # гарантированная очистка in-memory графа

    comm_count, modularity, written, levels = (
        rows[0] if rows else (0, 0.0, 0, 0)
    )
    sizes = _community_rows(store)
    communities: list[dict] = []
    for c, size in sizes:
        if int(size) < min_size:
            continue
        cid = int(c)
        communities.append(
            {
                "community_id": cid,
                "size": int(size),
                "top_entities": _top_entities(store, cid),
            }
        )
        if len(communities) >= top_communities:
            break

    _log.info(
        "gds_live.louvain",
        run_id=run_id,
        communities=int(comm_count),
        modularity=float(modularity),
        written=int(written),
        projected_nodes=proj["nodes"],
    )
    return {
        "run_id": run_id,
        "projected": proj,
        "community_count": int(comm_count),
        "modularity": round(float(modularity), 4),
        "levels": int(levels),
        "nodes_written": int(written),
        "communities": communities,
    }


@router.get("/communities")
def communities(
    min_size: int = Query(default=1, ge=1, le=100),
    limit: int = Query(default=24, ge=1, le=200),
    auto: bool = Query(default=True, description="запустить Louvain, если ещё не считали"),
) -> dict:
    """Легенда сообществ: id + размер + представительные сущности (§3.14/§17).

    Если корпус ещё не кластеризован и ``auto=true`` — лениво запускаем Louvain
    один раз. Крупные сообщества первыми — под цветную легенду 3D-клубка.
    """
    store = _require_server()
    rows = _community_rows(store)
    if not rows and auto:
        louvain(min_size=min_size, top_communities=limit)
        rows = _community_rows(store)
    out: list[dict] = []
    for c, size in rows:
        if int(size) < min_size:
            continue
        cid = int(c)
        out.append(
            {
                "community_id": cid,
                "size": int(size),
                "top_entities": _top_entities(store, cid),
            }
        )
        if len(out) >= limit:
            break
    return {"clustered": bool(rows), "count": len(out), "communities": out}


@router.get("/colored-graph", response_model=GraphResponse)
def colored_graph(
    limit: int = Query(default=400, ge=10, le=1500, description="узлов в клубке"),
    auto: bool = Query(default=True),
) -> GraphResponse:
    """Подграф самых связанных узлов с ``community_id`` для раскраски 3D-клубка.

    Берём топ-N узлов по степени (самые «живые» в клубке), тянем их рёбра и
    отдаём как обычный ``GraphResponse`` — каждый узел несёт ``communityId``,
    поэтому ``ForceGraph3D`` окрашивает его в цвет сообщества. Если кластеров
    ещё нет и ``auto=true`` — сперва прогоняем Louvain.
    """
    store = _require_server()
    if auto and not _community_rows(store):
        louvain()
    # Топ узлов по степени — самый информативный срез большого графа для клубка.
    rows = _gds(
        store,
        "MATCH (n:Node) "
        "OPTIONAL MATCH (n)-[r:Rel]-() "
        "WITH n, count(r) AS deg "
        "ORDER BY deg DESC "
        f"LIMIT {int(limit)} "
        "RETURN n.id AS id",
    )
    node_ids = [str(r[0]) for r in rows if r and r[0]]
    if not node_ids:
        return GraphResponse(nodes=[], edges=[])
    return store.subgraph_from_ids(node_ids, expand=0)


@router.get("/similar")
def similar(
    seed: str = Query(..., description="id узла-источника (обычно Material)"),
    k: int = Query(default=10, ge=1, le=50, description="topK похожих"),
) -> dict:
    """«Похожие материалы» через живой ``gds.nodeSimilarity`` (Jaccard соседств, §3.14/§11).

    Полный цикл: project → ``gds.nodeSimilarity.stream(topK)`` с фильтром по seed
    → drop. Возвращает похожие узлы с именем/типом и оценкой сходства — вход для
    «similar materials» (§17) и кандидатов missing-link (§11).
    """
    store = _require_server()
    if store.get_node(seed) is None:
        raise HTTPException(status_code=404, detail="seed node not found")

    proj = _project(store)
    try:
        rows = _gds(
            store,
            "CALL gds.nodeSimilarity.stream($g, {topK: $k}) "
            "YIELD node1, node2, similarity "
            "WITH gds.util.asNode(node1) AS a, gds.util.asNode(node2) AS b, similarity "
            "WHERE a.id = $seed "
            "RETURN b.id AS id, b.name AS name, b.label AS label, similarity "
            "ORDER BY similarity DESC "
            f"LIMIT {int(k)}",
            {"g": proj["name"], "k": int(k), "seed": seed},
        )
    finally:
        _drop_projection(store, proj["name"])

    node = store.get_node(seed)
    similar_nodes = [
        {
            "id": str(r[0]),
            "name": (r[1] or str(r[0])),
            "label": r[2],
            "similarity": round(float(r[3]), 4),
        }
        for r in rows
    ]
    _log.info("gds_live.similar", seed=seed, found=len(similar_nodes), projected=proj["nodes"])
    return {
        "seed": {"id": seed, "name": node.get("name"), "label": node.get("label")},
        "count": len(similar_nodes),
        "similar": similar_nodes,
    }

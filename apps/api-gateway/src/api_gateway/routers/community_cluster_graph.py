"""Community-cluster overview graph — GraphRAG Mode C «глобальный взгляд» (§11.8 / §5.3).

Строит компактную *мета-карту корпуса*: один узел на каждый кластер знаний
(community), рёбра между кластерами — агрегированное число связей между их
сущностями (какие кластеры «соприкасаются»). Это тот самый wow «global view of
corpus» из §11.8: вместо 30k-узлового клубка (`/graph/corpus/overview`,
``LargeGraphView``) фронт рисует десятки узлов-сообществ с иерархией/связями и
top-сущностями — обзорный ответ Mode C становится интерактивным графом.

Отличие от соседей:
- ``/graph-communities`` (``community_panel``) — текстовые сводки + подграф ОДНОГО
  сообщества (сущности внутри кластера);
- ``/gds-live`` — раскраска живого клубка по ``community_id`` (узлы = сущности);
- здесь узлы = САМИ КЛАСТЕРЫ, рёбра = связи между кластерами (мета-граф).

Payload — Reagraph-shaped (``nodes[]`` / ``edges[]``, §5.3), совместим и с
Sigma.js/Graphology fallback (§18 «Graph becomes unreadable → community view»).
Типы узлов/рёбер берём из :mod:`kg_retrievers.community_view_payload`
(``community``/``entity`` · ``INCLUDES_ENTITY``); межкластерное ребро — ``RELATED``.

Работает на обоих профилях: читает уже посчитанный ``community_id`` (его пишут
`gds.louvain` на server-профиле, §3.14, или embedded ``detect_communities``, §11).
Если корпус ещё не кластеризован — лениво запускаем ту же ``detect_communities``,
что и ``community_panel`` (общий store, общий источник кластеров). Роутер только
читает граф — рёбер/узлов в БД не создаёт.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api_gateway.deps import get_store
from kg_common import get_logger
from kg_retrievers.community_view_payload import (
    community_node_id,
    entity_node_id,
)

router = APIRouter(prefix="/api/v1/community-cluster-graph", tags=["community-cluster-graph"])

_log = get_logger("api.community_cluster_graph")

# Ярлык артефакта-сводки (его пишет detect_communities) — не сущность-участник.
_FINDING = "Finding"
# Тип межкластерного ребра мета-графа (§5.3 расширение community-view).
_RELATED = "RELATED"


def _cluster_rows(store: Any) -> list[list[Any]]:
    """(community_id, name, domain, evidence_count) по всем кластеризованным сущностям.

    Один проход по узлам с ``community_id`` (Finding-сводки исключены) — из него в
    Python считаем размер кластера, домены и top-сущности. Дешевле, чем N+1
    запросов на кластер. ``coalesce`` защищает от NULL-имён/доменов.
    """
    return store.rows(
        "MATCH (n:Node) WHERE n.community_id IS NOT NULL AND n.label <> $f "
        "RETURN n.community_id, coalesce(n.name,''), coalesce(n.domain,''), "
        "coalesce(n.evidence_count,0)",
        {"f": _FINDING},
    )


def _inter_cluster_rows(store: Any) -> list[list[Any]]:
    """(community_a, community_b, weight) — число связей между парами кластеров.

    Ненаправленный ``-[r:Rel]-`` с фильтром ``ca < cb`` считает каждую межкластерную
    связь один раз (ориентация ca<cb проходит, обратная — нет). ``count(r)``
    схлопывает всё до уровня пары кластеров, поэтому наружу отдаётся не «все рёбра»,
    а ~communities² пар — компактно даже на большом корпусе.
    """
    return store.rows(
        "MATCH (a:Node)-[r:Rel]-(b:Node) "
        "WHERE a.community_id IS NOT NULL AND b.community_id IS NOT NULL "
        "AND a.community_id < b.community_id "
        "RETURN a.community_id, b.community_id, count(r)",
        {},
    )


def _summary_titles(store: Any) -> dict[int, str]:
    """community_id → заголовок сводки (Finding.name), если detect_communities её писал."""
    rows = store.rows(
        "MATCH (f:Node) WHERE f.label=$f AND f.community_id IS NOT NULL "
        "RETURN f.community_id, coalesce(f.name,'')",
        {"f": _FINDING},
    )
    return {int(cid): str(name) for cid, name in rows if name}


def _ensure_clustered(store: Any, *, min_size: int) -> list[list[Any]]:
    """Прочитать кластеры; если корпус ни разу не кластеризован — лениво посчитать.

    Делегируем в ту же :func:`detect_communities`, что и ``community_panel``, чтобы
    мета-граф и текстовые сводки читали один источник ``community_id``.
    """
    rows = _cluster_rows(store)
    if rows:
        return rows
    from kg_retrievers.community import detect_communities

    detect_communities(store, min_size=min_size)
    return _cluster_rows(store)


def _aggregate(
    rows: list[list[Any]],
) -> dict[int, dict[str, Any]]:
    """Свернуть построчные (cid, name, domain, evidence) в карточку кластера."""
    clusters: dict[int, dict[str, Any]] = {}
    for cid_raw, name, domain, ev in rows:
        cid = int(cid_raw)
        c = clusters.setdefault(
            cid,
            {"size": 0, "domains": {}, "entities": []},
        )
        c["size"] += 1
        if domain:
            c["domains"][str(domain)] = c["domains"].get(str(domain), 0) + 1
        if name:
            c["entities"].append((str(name), float(ev or 0)))
    return clusters


@router.get("")
def cluster_graph(
    min_size: int = Query(default=2, ge=1, le=50, description="мин. размер кластера"),
    limit: int = Query(default=40, ge=1, le=200, description="сколько кластеров-узлов"),
    max_entities: int = Query(
        default=6, ge=0, le=20, description="top-сущностей на кластер (0 = без entity-узлов)"
    ),
    include_entities: bool = Query(
        default=False, description="добавить top-сущности как узлы с INCLUDES_ENTITY"
    ),
    min_weight: int = Query(default=1, ge=1, le=100, description="мин. вес межкластерного ребра"),
) -> dict:
    """Мета-граф кластеров знаний для UI Mode C (§11.8 / §5.3).

    Возвращает Reagraph-shaped ``nodes``/``edges``: узлы-сообщества (размер = число
    сущностей, домены, top-сущности), межкластерные рёбра ``RELATED`` с весом. При
    ``include_entities=true`` добавляет top-сущности как ``entity``-узлы с рёбрами
    ``INCLUDES_ENTITY`` (полная схема §5.3). Если корпус не кластеризован — лениво
    запускается детекция сообществ.
    """
    store = get_store()
    rows = _ensure_clustered(store, min_size=min_size)
    clustered = bool(rows)
    clusters = _aggregate(rows)

    # Топ-N кластеров по размеру, но не меньше min_size.
    ranked = sorted(
        (
            (cid, c)
            for cid, c in clusters.items()
            if c["size"] >= min_size
        ),
        key=lambda kv: kv[1]["size"],
        reverse=True,
    )
    kept = ranked[:limit]
    kept_ids = {cid for cid, _ in kept}
    titles = _summary_titles(store)

    nodes: list[dict[str, Any]] = []
    entity_edges: list[dict[str, Any]] = []
    seen_entity_nodes: set[str] = set()

    for cid, c in kept:
        # top-сущности кластера: по evidence_count, затем по имени (детерминированно).
        top = sorted(set(c["entities"]), key=lambda ne: (-ne[1], ne[0]))
        top_names = [n for n, _ in top[:max_entities]] if max_entities else []
        domains = sorted(c["domains"], key=lambda d: (-c["domains"][d], d))
        nodes.append(
            {
                "id": community_node_id(cid),
                "label": titles.get(cid) or f"Кластер знаний #{cid}",
                "type": "community",
                "community_id": cid,
                "size": c["size"],
                "domains": domains,
                "top_entities": top_names,
            }
        )
        if include_entities:
            for name in top_names:
                enode = entity_node_id(name)
                if enode not in seen_entity_nodes:
                    seen_entity_nodes.add(enode)
                    nodes.append(
                        {"id": enode, "label": name, "type": "entity", "community_id": cid}
                    )
                entity_edges.append(
                    {
                        "source": community_node_id(cid),
                        "target": enode,
                        "type": "INCLUDES_ENTITY",
                        "weight": 1,
                    }
                )

    # Межкластерные рёбра — только между оставленными кластерами и выше порога веса.
    edges: list[dict[str, Any]] = []
    for ca_raw, cb_raw, w_raw in _inter_cluster_rows(store):
        ca, cb, w = int(ca_raw), int(cb_raw), int(w_raw)
        if ca not in kept_ids or cb not in kept_ids or w < min_weight:
            continue
        edges.append(
            {
                "source": community_node_id(ca),
                "target": community_node_id(cb),
                "type": _RELATED,
                "weight": w,
            }
        )
    edges.sort(key=lambda e: e["weight"], reverse=True)
    edges.extend(entity_edges)

    _log.info(
        "community_cluster_graph.build",
        clustered=clustered,
        total_communities=len(clusters),
        communities=len(kept),
        nodes=len(nodes),
        related_edges=len(edges) - len(entity_edges),
        include_entities=include_entities,
    )
    return {
        "clustered": clustered,
        "total_communities": len(clusters),
        "count": len(kept),
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "clustered_nodes": sum(c["size"] for c in clusters.values()),
            "related_edges": len(edges) - len(entity_edges),
            "entity_edges": len(entity_edges),
        },
    }

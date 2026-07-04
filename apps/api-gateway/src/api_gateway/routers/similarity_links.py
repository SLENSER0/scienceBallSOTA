"""Граф-подсказки недостающих связей через node-similarity / KNN (§3.14, §11, §17).

«Граф не только помнит — он предполагает». По реальной топологии графа находим
узлы, *похожие* на seed (общие соседи → мера Jaccard, это дефолтная метрика
``gds.nodeSimilarity``), а затем переносим связи похожих узлов на seed:

    материалы, похожие на «X», связаны с лабораторией L →
    вероятно, «X» тоже относится к L, хотя ребро не проведено.

Это item-based collaborative filtering поверх KG — killer-надстройка над картой
пробелов: система подсказывает *следующий* эксперимент / связь.

Два пути расчёта, один результат:

* **GDS** — на server-профиле (Neo4j :8000) с установленным плагином Graph Data
  Science используется ``gds.nodeSimilarity.stream`` (метрика JACCARD) на
  UNDIRECTED-проекции ``Node``/``Rel``; in-memory граф всегда освобождается в
  ``finally`` (``gds.graph.drop``) — критерий приёмки §3.14.
* **In-process** — если плагина нет (или включён embedded/Kuzu профиль §12.8),
  та же мера Jaccard считается напрямую из ``store.rows`` по множествам соседей.
  Математически идентична GDS-метрике, поэтому фича работает на любом профиле.

Метод, которым получен ответ, честно возвращается в поле ``method``.

Отдельный префикс ``/similarity-links`` — не конфликтует с топологическим
``/link-prediction`` (§13.11, pairwise Adamic/Adar), который решает смежную, но
другую задачу (score конкретной пары, а не перенос связей по аналогии).
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterable

from fastapi import APIRouter, HTTPException, Query

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/similarity-links", tags=["similarity-links"])

# Метки, которые логично «дорисовывать» seed-узлу по аналогии с похожими.
_TARGET_LABELS = ("Lab", "Property", "ProcessingRegime", "Equipment", "Material", "Method")

# Включить попытку GDS-ускорения (по умолчанию да; отключаемо для отладки).
_USE_GDS = os.getenv("SB_SIMLINKS_USE_GDS", "1").lower() not in {"0", "false", "no"}


# --------------------------------------------------------------------------- #
# In-process node-similarity (Jaccard of neighbourhoods) — §12.8 fallback path #
# --------------------------------------------------------------------------- #
def _neighbors(store, node_id: str) -> set[str]:
    rows = store.rows(
        "MATCH (n:Node {id:$id})-[:Rel]-(m:Node) WHERE m.id <> $id RETURN DISTINCT m.id",
        {"id": node_id},
    )
    return {r[0] for r in rows}


def _peer_candidates(store, node_id: str, limit: int) -> list[tuple[str, str, str]]:
    """Узлы на расстоянии 2 (есть общий сосед) — пространство «похожих» кандидатов."""
    rows = store.rows(
        "MATCH (s:Node {id:$id})-[:Rel]-(:Node)-[:Rel]-(c:Node) "
        "WHERE c.id <> $id "
        f"RETURN DISTINCT c.id, c.name, c.label LIMIT {int(limit)}",
        {"id": node_id},
    )
    return [(r[0], r[1], r[2]) for r in rows]


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    return (len(a & b) / len(union)) if union else 0.0


def _similar_in_process(
    store, seed: str, k: int, same_label: str | None
) -> list[dict]:
    """Top-k похожих на ``seed`` узлов по Jaccard соседств (эквивалент nodeSimilarity)."""
    seed_nb = _neighbors(store, seed)
    if not seed_nb:
        return []
    out: list[dict] = []
    for cid, cname, clabel in _peer_candidates(store, seed, limit=600):
        if same_label and clabel != same_label:
            continue
        sim = _jaccard(seed_nb, _neighbors(store, cid))
        if sim <= 0:
            continue
        out.append(
            {"id": cid, "name": cname, "label": clabel, "similarity": round(sim, 4)}
        )
    out.sort(key=lambda d: d["similarity"], reverse=True)
    return out[: max(1, k)]


# --------------------------------------------------------------------------- #
# GDS-accelerated node-similarity — server profile (Neo4j) with GDS plugin     #
# --------------------------------------------------------------------------- #
def _similar_gds(store, seed: str, k: int, same_label: str | None) -> list[dict] | None:
    """Top-k похожих через ``gds.nodeSimilarity.stream``; None при недоступности GDS.

    Проекция ``Node``/``Rel`` (UNDIRECTED) создаётся под уникальным именем и
    ВСЕГДА удаляется в ``finally`` — после job ``gds.graph.list`` не растёт (§3.14).
    """
    execute = getattr(store, "execute", None)
    if execute is None:  # только Neo4jGraphStore умеет исполнять GDS-процедуры
        return None
    graph_name = f"simlinks-{abs(hash(seed)) % 10_000_000}"
    try:
        execute(
            "CALL gds.graph.project($g, 'Node', "
            "{Rel: {orientation: 'UNDIRECTED'}})",
            {"g": graph_name},
        )
        records = execute(
            "CALL gds.nodeSimilarity.stream($g, "
            "{topK: $k, similarityCutoff: 0.0, similarityMetric: 'JACCARD'}) "
            "YIELD node1, node2, similarity "
            "WITH gds.util.asNode(node1) AS a, gds.util.asNode(node2) AS b, similarity "
            "WHERE a.id = $seed "
            "RETURN b.id AS id, b.name AS name, b.label AS label, similarity "
            "ORDER BY similarity DESC LIMIT $lim",
            {"g": graph_name, "k": max(k, 25), "seed": seed, "lim": max(1, k) * 4},
        )
    except Exception:  # GDS плагина нет / другая версия → fallback
        return None
    finally:
        with contextlib.suppress(Exception):
            execute("CALL gds.graph.drop($g, false)", {"g": graph_name})

    out: list[dict] = []
    for rec in records:
        label = rec["label"]
        if same_label and label != same_label:
            continue
        out.append(
            {
                "id": rec["id"],
                "name": rec["name"],
                "label": label,
                "similarity": round(float(rec["similarity"]), 4),
            }
        )
    return out[: max(1, k)]


def _similar(store, seed: str, k: int, same_label: str | None) -> tuple[list[dict], str]:
    """Похожие узлы + метод расчёта (``gds`` | ``in_process``)."""
    if _USE_GDS:
        gds = _similar_gds(store, seed, k, same_label)
        if gds is not None:
            return gds, "gds"
    return _similar_in_process(store, seed, k, same_label), "in_process"


# --------------------------------------------------------------------------- #
# Routes                                                                       #
# --------------------------------------------------------------------------- #
@router.get("/seeds")
def seeds(label: str = "Material", limit: int = 100) -> dict:
    """Узлы, для которых имеет смысл искать похожих / подсказывать связи."""
    store = get_store()
    where = "n.label = $lab" if label else "n.label IS NOT NULL"
    params: dict = {"lab": label} if label else {}
    rows = store.rows(
        f"MATCH (n:Node) WHERE {where} RETURN n.id, n.name, n.label LIMIT {int(limit)}",
        params,
    )
    return {
        "count": len(rows),
        "seeds": [{"id": r[0], "name": r[1], "label": r[2]} for r in rows],
    }


@router.get("/similar")
def similar(
    seed: str = Query(..., description="id узла (обычно Material)"),
    k: int = Query(10, ge=1, le=50),
    same_label: bool = Query(
        True, description="искать похожих только той же метки, что и seed"
    ),
) -> dict:
    """KNN по node-similarity: узлы, наиболее похожие на ``seed`` по соседству (§17)."""
    store = get_store()
    node = store.get_node(seed)
    if node is None:
        raise HTTPException(status_code=404, detail="seed node not found")
    label = node.get("label") if same_label else None
    peers, method = _similar(store, seed, k, label)
    return {
        "seed": {"id": seed, "name": node.get("name"), "label": node.get("label")},
        "method": method,
        "count": len(peers),
        "similar": peers,
    }


def _existing_targets(store, seed: str) -> set[str]:
    return _neighbors(store, seed)


def _peer_target_rows(
    store, peer_ids: Iterable[str], target_label: str | None
) -> list[tuple[str, str, str, str]]:
    """Для каждого похожего узла — его соседи-кандидаты (peer_id, t_id, t_name, t_label)."""
    ids = list(peer_ids)
    if not ids:
        return []
    where = " AND t.label = $tl" if target_label else ""
    params: dict = {"ids": ids}
    if target_label:
        params["tl"] = target_label
    rows = store.rows(
        "MATCH (p:Node)-[:Rel]-(t:Node) "
        f"WHERE p.id IN $ids AND t.id <> p.id{where} "
        "RETURN p.id, t.id, t.name, t.label",
        params,
    )
    return [(r[0], r[1], r[2], r[3]) for r in rows]


@router.get("/suggest")
def suggest(
    seed: str = Query(..., description="id узла-источника (обычно Material)"),
    target_label: str | None = Query(
        None, description="фильтр метки предлагаемой связи, напр. Lab"
    ),
    k: int = Query(12, ge=1, le=50, description="сколько похожих узлов учитывать"),
    limit: int = Query(12, ge=1, le=50, description="сколько связей предложить"),
) -> dict:
    """Killer §3.14: недостающие связи ``seed`` по аналогии с похожими узлами.

    Алгоритм (item-based CF поверх KG):

    1. находим top-``k`` похожих на ``seed`` узлов (node-similarity / KNN);
    2. смотрим их связи ``target`` (с фильтром ``target_label``), которых у
       ``seed`` ещё нет;
    3. score(target) = Σ similarity(seed, peer) по похожим, ведущим к target;
    4. ранжируем, нормируем в [0, 1], объясняем «кем подсказано».
    """
    store = get_store()
    node = store.get_node(seed)
    if node is None:
        raise HTTPException(status_code=404, detail="seed node not found")
    if target_label and target_label not in _TARGET_LABELS:
        pass  # свободная метка допустима — подсказка не жёсткая

    # 1. похожие узлы той же метки (материалы, похожие на seed-материал)
    peers, method = _similar(store, seed, k, node.get("label"))
    if not peers:
        return {
            "seed": {"id": seed, "name": node.get("name"), "label": node.get("label")},
            "method": method,
            "target_label": target_label,
            "count": 0,
            "suggestions": [],
        }
    sim_by_peer = {p["id"]: p["similarity"] for p in peers}
    name_by_peer = {p["id"]: (p["name"] or p["id"]) for p in peers}

    # 2/3. переносим связи похожих на seed, суммируя similarity как «уверенность»
    existing = _existing_targets(store, seed)
    existing.add(seed)
    agg: dict[str, dict] = {}
    for pid, tid, tname, tlabel in _peer_target_rows(store, sim_by_peer, target_label):
        if tid in existing:
            continue  # связь уже проведена — не «недостающая»
        entry = agg.setdefault(
            tid,
            {
                "target": tid,
                "target_name": tname,
                "target_label": tlabel,
                "raw_score": 0.0,
                "supporters": [],
            },
        )
        entry["raw_score"] += sim_by_peer.get(pid, 0.0)
        entry["supporters"].append(
            {"id": pid, "name": name_by_peer.get(pid, pid), "similarity": sim_by_peer[pid]}
        )

    suggestions = list(agg.values())
    for s in suggestions:
        s["supporters"].sort(key=lambda x: x["similarity"], reverse=True)
        s["support_count"] = len(s["supporters"])
        s["raw_score"] = round(s["raw_score"], 4)
    suggestions.sort(key=lambda s: (s["raw_score"], s["support_count"]), reverse=True)
    suggestions = suggestions[: max(1, limit)]

    top = suggestions[0]["raw_score"] if suggestions else 0.0
    seed_name = node.get("name") or seed
    for s in suggestions:
        s["score"] = round(s["raw_score"] / top, 4) if top > 0 else 0.0
        lead = s["supporters"][0]["name"] if s["supporters"] else "похожие узлы"
        extra = (
            f" и ещё {s['support_count'] - 1}" if s["support_count"] > 1 else ""
        )
        s["reason"] = (
            f"«{lead}»{extra} — похоже на «{seed_name}» и связано с "
            f"«{s['target_name'] or s['target']}»; вероятно, связь есть, но не зафиксирована"
        )

    return {
        "seed": {"id": seed, "name": node.get("name"), "label": node.get("label")},
        "method": method,
        "target_label": target_label,
        "count": len(suggestions),
        "suggestions": suggestions,
    }

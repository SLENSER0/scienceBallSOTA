"""Корпусная доска предсказанных недостающих связей — GDS nodeSimilarity/KNN (§3.14).

«Граф не только помнит — он предполагает». В отличие от per-seed подсказок
(``/api/v1/similarity-links``, где пользователь уже выбрал материал), эта ручка
проактивно сканирует ВЕСЬ граф и выдаёт глобально самые сильные *неявные*
связи: пары узлов, которые по топологии очень похожи (много общих соседей →
высокий Jaccard, метрика по умолчанию ``gds.nodeSimilarity``), но прямого ребра
между ними ещё нет. Такая пара — сильнейший кандидат в «недостающую связь»:

    материал A и материал B делят 7 общих режимов/лабораторий/свойств, но
    напрямую не связаны → вероятно, между ними есть связь, ещё не зафиксированная.

Это «лента открытий» над картой пробелов: не нужно знать, что искать — граф сам
подсказывает, какую связь проверить следующей. Рёбер модуль не создаёт (§3.14 —
только предсказание, запись остаётся за куратором §3.7).

Два пути расчёта, один результат (поле ``method`` честно сообщает, каким считали):

* **GDS** — server-профиль (Neo4j :8000, плагин Graph Data Science, §3.9):
  ``gds.graph.project`` (UNDIRECTED ``Node``/``Rel``) → ``gds.nodeSimilarity.stream``
  (JACCARD, topK) → фильтр «нет прямого ребра» → глобальный рейтинг. In-memory
  граф ВСЕГДА освобождается в ``finally`` (``gds.graph.drop``) — критерий приёмки
  §3.14 (``gds.graph.list`` пуст после job).
* **In-process** — если GDS-плагина нет или активен embedded/Kuzu профиль (§12.8):
  тот же Jaccard соседств считается напрямую из ``store.rows`` по выборке
  seed-узлов. Математически идентичен GDS-метрике.

Детальные индексы близости для конкретной пары (``/pair``) переиспользуют
готовый ``kg_retrievers.link_prediction.score_pair`` (common / Adamic-Adar /
resource-allocation / preferential) — не переписываем, а дополняем.

Отдельный префикс ``/api/v1/missing-links`` — не конфликтует с
``/similarity-links`` (per-seed CF), ``/link-prediction`` (pairwise score) и
``/gds-live`` (Louvain-раскраска).
"""

from __future__ import annotations

import contextlib
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_gateway.deps import get_store
from kg_common import get_logger, get_settings, make_id
from kg_retrievers.link_prediction import score_pair

router = APIRouter(prefix="/api/v1/missing-links", tags=["missing-links"])

_log = get_logger("api.missing_links")

# Метки, которые осмысленно предсказывать «дорисованными» связями.
_KNOWN_LABELS = (
    "Material",
    "Lab",
    "Property",
    "ProcessingRegime",
    "Equipment",
    "Method",
)


def _is_server() -> bool:
    return get_settings().runtime_profile == "server"


# --------------------------------------------------------------------------- #
# GDS path (server profile, Neo4j + Graph Data Science plugin)                 #
# --------------------------------------------------------------------------- #
def _board_gds(
    store: Any,
    *,
    seed_label: str | None,
    target_label: str | None,
    top_k: int,
    cutoff: float,
    limit: int,
) -> list[dict] | None:
    """Глобальный топ предсказанных недостающих связей через ``gds.nodeSimilarity``.

    Возвращает ``None``, если GDS недоступен (плагина нет / другая версия) — тогда
    вызывающий переходит на in-process путь. In-memory проекция удаляется в
    ``finally`` при любом исходе (§3.14).
    """
    graph_name = f"sb_missing_links_{make_id('Finding', 'ml')[-8:]}"
    try:
        store.rows(
            "CALL gds.graph.project($g, 'Node', {Rel: {orientation: 'UNDIRECTED'}})",
            {"g": graph_name},
        )
        rows = store.rows(
            "CALL gds.nodeSimilarity.stream($g, "
            "{topK: $topk, similarityCutoff: $cut, similarityMetric: 'JACCARD'}) "
            "YIELD node1, node2, similarity "
            "WITH gds.util.asNode(node1) AS a, gds.util.asNode(node2) AS b, similarity "
            # a.id < b.id — каждая неориентированная пара ровно один раз
            "WHERE a.id < b.id AND NOT (a)-[:Rel]-(b) "
            "AND ($seed_label IS NULL OR a.label = $seed_label OR b.label = $seed_label) "
            "AND ($target_label IS NULL OR a.label = $target_label "
            "     OR b.label = $target_label) "
            # общие соседи — объяснение подсказки
            "WITH a, b, similarity, "
            "     [(a)-[:Rel]-(x:Node) WHERE (x)-[:Rel]-(b) | x.name] AS shared_names "
            "RETURN a.id AS a_id, a.name AS a_name, a.label AS a_label, "
            "       b.id AS b_id, b.name AS b_name, b.label AS b_label, "
            "       similarity AS sim, size(shared_names) AS shared, "
            "       shared_names[0..4] AS via "
            "ORDER BY similarity DESC, shared DESC "
            "LIMIT $limit",
            {
                "g": graph_name,
                "topk": int(top_k),
                "cut": float(cutoff),
                "seed_label": seed_label,
                "target_label": target_label,
                "limit": int(limit),
            },
        )
    except Exception as exc:  # плагина нет / другая версия GDS → fallback
        _log.warning("missing_links.gds_unavailable", error=str(exc)[:200])
        return None
    finally:
        with contextlib.suppress(Exception):
            store.rows("CALL gds.graph.drop($g, false)", {"g": graph_name})

    out: list[dict] = []
    for r in rows:
        a_id, a_name, a_label, b_id, b_name, b_label, sim, shared, via = r
        out.append(
            _pack(
                a_id,
                a_name,
                a_label,
                b_id,
                b_name,
                b_label,
                float(sim),
                int(shared),
                [v for v in (via or []) if v],
            )
        )
    return out


# --------------------------------------------------------------------------- #
# In-process path (embedded / Kuzu, or GDS plugin missing) — §12.8            #
# --------------------------------------------------------------------------- #
def _neighbors(store: Any, node_id: str, cache: dict[str, set[str]]) -> set[str]:
    if node_id not in cache:
        rows = store.rows(
            "MATCH (n:Node {id:$id})-[:Rel]-(m:Node) WHERE m.id <> $id "
            "RETURN DISTINCT m.id",
            {"id": node_id},
        )
        cache[node_id] = {r[0] for r in rows}
    return cache[node_id]


def _seed_nodes(store: Any, seed_label: str | None, sample: int) -> list[tuple[str, str, str]]:
    """Seed-узлы для сканирования: по метке (если задана) — самые связанные первыми."""
    where = "n.label = $lab" if seed_label else "n.label IS NOT NULL"
    params: dict = {"lab": seed_label} if seed_label else {}
    # степень как приоритет — у хабов больше шансов на осмысленные недостающие связи
    try:
        rows = store.rows(
            f"MATCH (n:Node) WHERE {where} "
            "OPTIONAL MATCH (n)-[r:Rel]-() "
            "WITH n, count(r) AS deg "
            "ORDER BY deg DESC "
            f"LIMIT {int(sample)} "
            "RETURN n.id, n.name, n.label",
            params,
        )
    except Exception:  # некоторые сторы не любят OPTIONAL MATCH+agg → простой срез
        rows = store.rows(
            f"MATCH (n:Node) WHERE {where} RETURN n.id, n.name, n.label LIMIT {int(sample)}",
            params,
        )
    return [(r[0], r[1], r[2]) for r in rows]


def _two_hop(store: Any, node_id: str, cap: int) -> list[tuple[str, str, str]]:
    rows = store.rows(
        "MATCH (s:Node {id:$id})-[:Rel]-(:Node)-[:Rel]-(c:Node) "
        f"WHERE c.id <> $id RETURN DISTINCT c.id, c.name, c.label LIMIT {int(cap)}",
        {"id": node_id},
    )
    return [(r[0], r[1], r[2]) for r in rows]


def _board_in_process(
    store: Any,
    *,
    seed_label: str | None,
    target_label: str | None,
    cutoff: float,
    limit: int,
    sample: int,
) -> list[dict]:
    """Глобальный топ недостающих связей по Jaccard соседств — store-agnostic (§12.8).

    Сканируем выборку seed-узлов, для каждого берём кандидатов на расстоянии 2
    (есть общий сосед), считаем Jaccard, дедуплицируем неориентированные пары и
    ранжируем глобально. Множества соседей кэшируются, чтобы не перезапрашивать.
    """
    ncache: dict[str, set[str]] = {}
    meta: dict[str, tuple[str, str]] = {}  # id -> (name, label)
    best: dict[tuple[str, str], dict] = {}  # (min_id, max_id) -> результат

    for s_id, s_name, s_label in _seed_nodes(store, seed_label, sample):
        meta[s_id] = (s_name, s_label)
        s_nb = _neighbors(store, s_id, ncache)
        if not s_nb:
            continue
        for c_id, c_name, c_label in _two_hop(store, s_id, cap=250):
            if c_id == s_id or c_id in s_nb:
                continue  # прямое ребро уже есть — не «недостающая» связь
            if target_label and c_label != target_label and s_label != target_label:
                continue
            c_nb = _neighbors(store, c_id, ncache)
            inter = s_nb & c_nb
            if not inter:
                continue
            union = s_nb | c_nb
            sim = len(inter) / len(union) if union else 0.0
            if sim < cutoff:
                continue
            meta[c_id] = (c_name, c_label)
            key = (s_id, c_id) if s_id < c_id else (c_id, s_id)
            prev = best.get(key)
            if prev is None or sim > prev["similarity"]:
                best[key] = {
                    "_pair": key,
                    "similarity": round(sim, 4),
                    "shared": len(inter),
                    "_inter": inter,
                }

    ranked = sorted(
        best.values(), key=lambda d: (d["similarity"], d["shared"]), reverse=True
    )[: max(1, limit)]

    out: list[dict] = []
    for item in ranked:
        a_id, b_id = item["_pair"]
        a_name, a_label = meta.get(a_id, (a_id, None))
        b_name, b_label = meta.get(b_id, (b_id, None))
        via = _resolve_names(store, list(item["_inter"])[:4], ncache_meta=meta)
        out.append(
            _pack(
                a_id,
                a_name,
                a_label,
                b_id,
                b_name,
                b_label,
                item["similarity"],
                item["shared"],
                via,
            )
        )
    return out


def _resolve_names(
    store: Any, ids: list[str], *, ncache_meta: dict[str, tuple[str, str]]
) -> list[str]:
    """Имена нескольких общих соседей для объяснения (bounded — только для топа)."""
    names: list[str] = []
    for nid in ids:
        if nid in ncache_meta:
            names.append(ncache_meta[nid][0] or nid)
            continue
        node = store.get_node(nid)
        names.append((node.get("name") if node else None) or nid)
    return [n for n in names if n]


# --------------------------------------------------------------------------- #
# Shared shaping                                                               #
# --------------------------------------------------------------------------- #
def _pack(
    a_id: str,
    a_name: str | None,
    a_label: str | None,
    b_id: str,
    b_name: str | None,
    b_label: str | None,
    similarity: float,
    shared: int,
    via: list[str],
) -> dict:
    a_disp = a_name or a_id
    b_disp = b_name or b_id
    via_txt = ", ".join(f"«{v}»" for v in via[:3]) if via else "общих соседей"
    more = " и др." if shared > len(via[:3]) else ""
    reason = (
        f"«{a_disp}» и «{b_disp}» делят {shared} общих связей ({via_txt}{more}), "
        f"но напрямую не соединены — связь вероятна, но не зафиксирована"
    )
    return {
        "a": {"id": a_id, "name": a_disp, "label": a_label},
        "b": {"id": b_id, "name": b_disp, "label": b_label},
        "similarity": round(float(similarity), 4),
        "shared": int(shared),
        "shared_via": via[:4],
        "reason": reason,
    }


# --------------------------------------------------------------------------- #
# Routes                                                                       #
# --------------------------------------------------------------------------- #
@router.get("/status")
def status() -> dict:
    """Доступность живого GDS-пути и подсказка по методу расчёта доски."""
    server = _is_server()
    return {
        "profile": get_settings().runtime_profile,
        "gds_capable": server,
        "method": "gds" if server else "in_process",
        "labels": list(_KNOWN_LABELS),
        "note": (
            "На server-профиле доска считается живым gds.nodeSimilarity (JACCARD); "
            "на embedded — эквивалентным in-process Jaccard соседств."
        ),
    }


@router.get("/board")
def board(
    seed_label: str | None = Query(
        None, description="ограничить одну сторону пары меткой, напр. Material"
    ),
    target_label: str | None = Query(
        None, description="ограничить вторую сторону пары меткой, напр. Lab"
    ),
    top_k: int = Query(15, ge=1, le=50, description="topK для gds.nodeSimilarity"),
    min_similarity: float = Query(
        0.1, ge=0.0, le=1.0, description="порог Jaccard-сходства для кандидата"
    ),
    limit: int = Query(25, ge=1, le=100, description="сколько связей показать"),
    sample: int = Query(
        80, ge=10, le=400, description="сколько seed-узлов сканировать (in-process путь)"
    ),
) -> dict:
    """Корпусная лента предсказанных недостающих связей (§3.14).

    Глобальный рейтинг пар «очень похожи, но не соединены». На server-профиле —
    живой ``gds.nodeSimilarity`` с очисткой in-memory графа; при недоступности
    GDS честный in-process fallback. ``method`` в ответе сообщает, каким считали.
    """
    store = get_store()
    method = "in_process"
    predictions: list[dict] | None = None

    if _is_server():
        predictions = _board_gds(
            store,
            seed_label=seed_label,
            target_label=target_label,
            top_k=top_k,
            cutoff=min_similarity,
            limit=limit,
        )
        if predictions is not None:
            method = "gds"

    if predictions is None:
        predictions = _board_in_process(
            store,
            seed_label=seed_label,
            target_label=target_label,
            cutoff=min_similarity,
            limit=limit,
            sample=sample,
        )

    top = predictions[0]["similarity"] if predictions else 0.0
    for p in predictions:
        p["confidence"] = round(p["similarity"] / top, 4) if top > 0 else 0.0

    _log.info(
        "missing_links.board",
        method=method,
        seed_label=seed_label,
        target_label=target_label,
        count=len(predictions),
    )
    return {
        "method": method,
        "seed_label": seed_label,
        "target_label": target_label,
        "min_similarity": min_similarity,
        "count": len(predictions),
        "predictions": predictions,
    }


@router.get("/pair")
def pair(
    a: str = Query(..., description="id первого узла пары"),
    b: str = Query(..., description="id второго узла пары"),
) -> dict:
    """Детальные индексы близости для предсказанной пары — инспекция подсказки.

    Переиспользует ``kg_retrievers.link_prediction.score_pair`` (common / Jaccard /
    Adamic-Adar / resource-allocation / preferential), чтобы куратор мог оценить,
    насколько надёжна подсказка перед тем, как провести ребро вручную (§3.7).
    """
    store = get_store()
    na, nb = store.get_node(a), store.get_node(b)
    if na is None or nb is None:
        raise HTTPException(status_code=404, detail="node not found")
    ls = score_pair(store, a, b)
    already_linked = b in {
        r[0]
        for r in store.rows(
            "MATCH (n:Node {id:$id})-[:Rel]-(m:Node) RETURN DISTINCT m.id", {"id": a}
        )
    }
    return {
        "a": {"id": a, "name": na.get("name"), "label": na.get("label")},
        "b": {"id": b, "name": nb.get("name"), "label": nb.get("label")},
        "already_linked": already_linked,
        "indices": ls.as_dict(),
    }

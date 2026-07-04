"""Предсказание недостающих связей — link prediction, Mode D (§13.11, §10.1).

«Граф думает»: по топологии реального графа предлагаем вероятные, но пока не
проведённые связи material↔(lab / property / regime / equipment). Мы НЕ создаём
рёбер — только ранжируем кандидатов, чтобы подсказать следующий эксперимент.

Метод — классические индексы близости из
:mod:`kg_retrievers.link_prediction` (common neighbours, Jaccard, Adamic/Adar,
resource allocation, preferential attachment). Это NetworkX/in-process путь
§12.8: работает и на embedded-профиле (Kuzu), и на server-профиле (Neo4j) —
оба стора делят интерфейс ``store.rows`` (см. ``store_factory``), поэтому
никакого GDS-плагина для read-only проекции не требуется.

Отдельный префикс ``/link-prediction`` — не конфликтует с ``/graph`` и ``/gaps``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api_gateway.deps import get_store
from kg_retrievers.link_prediction import score_pair

router = APIRouter(prefix="/api/v1/link-prediction", tags=["link-prediction"])

# Метрики близости → поля LinkScore (см. kg_retrievers.link_prediction.LinkScore).
_METRICS = {"adamic_adar", "resource_allocation", "jaccard", "common", "preferential"}

# Метки, которые логично «дорисовывать» материалу (material↔property/lab/regime…).
_DEFAULT_TARGET_LABELS = ("Lab", "Property", "ProcessingRegime", "Equipment", "Material")


def _seed_rows(store, label: str | None, limit: int) -> list[list]:
    where = "n.label = $lab" if label else "n.label IS NOT NULL"
    params: dict = {"lab": label} if label else {}
    return store.rows(
        f"MATCH (n:Node) WHERE {where} RETURN n.id, n.name, n.label LIMIT {int(limit)}",
        params,
    )


def _direct_neighbor_ids(store, node_id: str) -> set[str]:
    rows = store.rows(
        "MATCH (n:Node {id:$id})-[:Rel]-(m:Node) WHERE m.id <> $id RETURN DISTINCT m.id",
        {"id": node_id},
    )
    return {r[0] for r in rows}


def _two_hop_candidates(store, node_id: str, limit: int) -> list[tuple[str, str, str]]:
    """Nodes sharing ≥1 neighbour with the seed (distance-2) — the search space
    for missing links. Returns (id, name, label) tuples."""
    rows = store.rows(
        "MATCH (s:Node {id:$id})-[:Rel]-(mid:Node)-[:Rel]-(c:Node) "
        "WHERE c.id <> $id "
        f"RETURN DISTINCT c.id, c.name, c.label LIMIT {int(limit)}",
        {"id": node_id},
    )
    return [(r[0], r[1], r[2]) for r in rows]


@router.get("/seeds")
def seeds(label: str = "Material", limit: int = 100) -> dict:
    """Узлы, для которых можно предсказывать связи (по умолчанию материалы)."""
    rows = _seed_rows(get_store(), label or None, limit)
    return {
        "count": len(rows),
        "seeds": [{"id": r[0], "name": r[1], "label": r[2]} for r in rows],
    }


@router.get("/predict")
def predict(
    seed: str = Query(..., description="id узла-источника (обычно Material)"),
    metric: str = "adamic_adar",
    target_label: str | None = Query(None, description="фильтр по метке кандидата"),
    limit: int = 12,
) -> dict:
    """Ранжированные вероятные, но отсутствующие связи от ``seed`` (Mode D §13.11).

    Кандидаты — узлы на расстоянии 2 (общий сосед есть, прямого ребра нет),
    отсортированные по метрике близости. ``score`` нормирован к [0, 1] по
    максимуму в выдаче — это «уверенность» подсказки для UI-бара.
    """
    if metric not in _METRICS:
        raise HTTPException(status_code=422, detail=f"metric must be one of {sorted(_METRICS)}")

    store = get_store()
    node = store.get_node(seed)
    if node is None:
        raise HTTPException(status_code=404, detail="seed node not found")
    if target_label and target_label not in _DEFAULT_TARGET_LABELS:
        # свободная метка тоже допустима, но подскажем каноничные
        pass

    direct = _direct_neighbor_ids(store, seed)
    raw = _two_hop_candidates(store, seed, limit=400)

    predictions = []
    for cid, cname, clabel in raw:
        if cid == seed or cid in direct:
            continue  # ребро уже существует — это не «недостающая» связь
        if target_label and clabel != target_label:
            continue
        ls = score_pair(store, seed, cid)
        raw_val = float(getattr(ls, metric))
        if raw_val <= 0:
            continue  # нет топологического сигнала → не предсказываем
        predictions.append(
            {
                "target": cid,
                "target_name": cname,
                "target_label": clabel,
                "metric": metric,
                "raw_score": round(raw_val, 4),
                "shared_neighbors": ls.common,
                "jaccard": round(ls.jaccard, 4),
                "adamic_adar": round(ls.adamic_adar, 4),
                "resource_allocation": round(ls.resource_allocation, 4),
                "preferential": ls.preferential,
                "reason": (
                    f"{ls.common} общих связей с «{node.get('name') or seed}» "
                    f"(Adamic/Adar {ls.adamic_adar:.2f}) — связь вероятна, но не проведена"
                ),
            }
        )

    predictions.sort(key=lambda p: p["raw_score"], reverse=True)
    predictions = predictions[: max(1, int(limit))]
    top = predictions[0]["raw_score"] if predictions else 0.0
    for p in predictions:
        p["score"] = round(p["raw_score"] / top, 4) if top > 0 else 0.0

    return {
        "seed": {"id": seed, "name": node.get("name"), "label": node.get("label")},
        "metric": metric,
        "target_label": target_label,
        "count": len(predictions),
        "predictions": predictions,
    }


@router.get("/pair")
def pair(a: str = Query(...), b: str = Query(...)) -> dict:
    """Сырые индексы близости для конкретной пары (a, b) — для инспекции."""
    store = get_store()
    if store.get_node(a) is None or store.get_node(b) is None:
        raise HTTPException(status_code=404, detail="node not found")
    ls = score_pair(store, a, b)
    return ls.as_dict()

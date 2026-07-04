"""«Похожие материалы» по режимам/свойствам — node-similarity (Mode D) как фича (§13.11).

Mode D graph-алгоритмы (node similarity) уже живут в бэке
(``kg_retrievers.graph_algos`` — NetworkX-Jaccard над Kuzu, §12.8; и живой
``gds.nodeSimilarity`` на Neo4j :8000, ``routers/gds_live.py``, ``routers/
similarity_links.py``), но «сырой» nodeSimilarity считает сходство по ЛЮБЫМ общим
соседям и не объясняет ПОЧЕМУ два материала похожи.

Этот роутер выводит node-similarity в UI под конкретный аналитический вопрос —
«Найди материалы, похожие на X по режимам обработки и свойствам» — и, главное,
ОБЪЯСНЯЕТ сходство: возвращает не только оценку, но и сами общие узлы,
сгруппированные по фасетам (ProcessingRegime / Property / Method / Equipment).

Метрика — тот же Jaccard, что и в ``gds.nodeSimilarity`` (метрика JACCARD по
умолчанию), но множество соседей ограничено «атрибутными» метками (фасетами), а
не всем графом. Поэтому результат — интерпретируемое «apples-to-apples» сходство:

    Material A ~ Material B, потому что делят режим «спекание 1200 °C»,
    свойство «плотность» и метод «SEM».

Считается напрямую из ``store.rows`` (Cypher по проекции ``:Node``/``:Rel``),
поэтому работает и на server-профиле (Neo4j), и на embedded (Kuzu) без GDS-плагина
— seed-локальная выборка (2 хопа) ограничена и дёшева даже на 66k-графе.

Отдельный префикс ``/similar-materials`` — не конфликтует с топологическим
``/similarity-links`` (перенос связей по аналогии, item-based CF) и generic
``/gds-live/similar``: тут фокус на объяснимом сходстве материалов по фасетам.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_gateway.deps import get_store
from kg_common import get_logger

router = APIRouter(prefix="/api/v1/similar-materials", tags=["similar-materials"])

_log = get_logger("api.similar_materials")

# Фасеты «атрибутов» материала, по которым считаем осмысленное сходство.
# Порядок = порядок отображения в UI.
_FACETS: tuple[str, ...] = ("ProcessingRegime", "Property", "Method", "Equipment")

# Человеко-читаемые подписи фасетов (для reason-строки на бэке).
_FACET_RU: dict[str, str] = {
    "ProcessingRegime": "режим",
    "Property": "свойство",
    "Method": "метод",
    "Equipment": "оборудование",
}


def _clean_facets(raw: str | None) -> list[str]:
    """Разобрать csv-список фасетов, оставив только валидные метки (иначе — все)."""
    if not raw:
        return list(_FACETS)
    wanted = [f.strip() for f in raw.split(",") if f.strip()]
    picked = [f for f in wanted if f in _FACETS]
    return picked or list(_FACETS)


def _attr_neighbours(store: Any, seed: str, facets: list[str]) -> list[tuple[str, str, str]]:
    """Атрибутные соседи seed (id, name, label) — множество для знаменателя Jaccard."""
    rows = store.rows(
        "MATCH (s:Node {id:$id})-[:Rel]-(a:Node) "
        "WHERE a.label IN $f AND a.id <> $id "
        "RETURN DISTINCT a.id, a.name, a.label",
        {"id": seed, "f": facets},
    )
    return [(r[0], r[1], r[2]) for r in rows]


def _shared_rows(
    store: Any, seed: str, facets: list[str], cand_cap: int
) -> list[tuple[str, str, str, str, str]]:
    """Материалы-кандидаты и общие с seed атрибутные узлы.

    Строки ``(cand_id, cand_name, attr_id, attr_name, attr_label)`` — каждая
    фиксирует один общий атрибут между seed и материалом-кандидатом (на
    расстоянии 2 хопа через общий атрибут). Кандидаты ограничены ``cand_cap``,
    чтобы выборка оставалась дешёвой на большом графе.
    """
    rows = store.rows(
        "MATCH (s:Node {id:$id})-[:Rel]-(a:Node)-[:Rel]-(c:Node) "
        "WHERE a.label IN $f AND a.id <> $id "
        "AND c.label = 'Material' AND c.id <> $id "
        "RETURN c.id, c.name, a.id, a.name, a.label "
        f"LIMIT {int(cand_cap)}",
        {"id": seed, "f": facets},
    )
    return [(r[0], r[1], r[2], r[3], r[4]) for r in rows]


def _cand_attr_counts(store: Any, cand_ids: list[str], facets: list[str]) -> dict[str, int]:
    """Размер атрибутного соседства каждого кандидата (знаменатель Jaccard)."""
    if not cand_ids:
        return {}
    rows = store.rows(
        "MATCH (c:Node)-[:Rel]-(a:Node) "
        "WHERE c.id IN $ids AND a.label IN $f AND a.id <> c.id "
        "RETURN c.id, count(DISTINCT a.id)",
        {"ids": cand_ids, "f": facets},
    )
    return {r[0]: int(r[1]) for r in rows}


def _facet_label(count_by_facet: dict[str, int]) -> str:
    """Короткая RU-подпись «2 режима · 1 свойство» для reason-строки."""
    parts = []
    for facet in _FACETS:
        n = count_by_facet.get(facet, 0)
        if n:
            parts.append(f"{n} {_FACET_RU[facet]}{'а' if 1 < n < 5 else ('ов' if n else '')}")
    return " · ".join(parts)


@router.get("/seeds")
def seeds(limit: int = Query(120, ge=1, le=500)) -> dict:
    """Материалы, у которых есть атрибуты (режимы/свойства) — осмысленные seed'ы.

    Отбираем :Material c хотя бы одним фасетным соседом и сортируем по числу
    атрибутов — «богатые» материалы дают самое информативное сравнение.
    """
    store = get_store()
    rows = store.rows(
        "MATCH (m:Node)-[:Rel]-(a:Node) "
        "WHERE m.label = 'Material' AND a.label IN $f AND a.id <> m.id "
        "WITH m, count(DISTINCT a.id) AS attrs "
        "RETURN m.id, m.name, attrs "
        "ORDER BY attrs DESC, m.name "
        f"LIMIT {int(limit)}",
        {"f": list(_FACETS)},
    )
    return {
        "count": len(rows),
        "seeds": [
            {"id": r[0], "name": r[1] or r[0], "attributes": int(r[2])} for r in rows
        ],
    }


@router.get("/similar")
def similar(
    seed: str = Query(..., description="id материала-источника"),
    k: int = Query(10, ge=1, le=50, description="сколько похожих материалов вернуть"),
    facets: str | None = Query(
        None,
        description="csv фасетов сравнения (ProcessingRegime,Property,Method,Equipment)",
    ),
    cand_cap: int = Query(4000, ge=200, le=20000, description="лимит выборки кандидатов"),
) -> dict:
    """Материалы, похожие на ``seed`` по фасетам, с объяснением общих узлов (§13.11).

    Node-similarity (Mode D) = Jaccard атрибутных соседств
    ``|shared| / (|seed_attrs| + |cand_attrs| − |shared|)`` — та же метрика, что
    ``gds.nodeSimilarity`` (JACCARD), но ограниченная выбранными фасетами. Для
    каждого похожего материала возвращаем сами общие узлы, сгруппированные по
    фасету, — «почему похоже».
    """
    store = get_store()
    node = store.get_node(seed)
    if node is None:
        raise HTTPException(status_code=404, detail="seed material not found")

    facet_list = _clean_facets(facets)
    seed_attrs = _attr_neighbours(store, seed, facet_list)
    seed_ids = {a[0] for a in seed_attrs}
    if not seed_ids:
        return {
            "seed": {"id": seed, "name": node.get("name") or seed, "label": node.get("label")},
            "facets": facet_list,
            "seed_attributes": [],
            "count": 0,
            "similar": [],
            "note": "у материала нет режимов/свойств для сравнения",
        }

    shared = _shared_rows(store, seed, facet_list, cand_cap)

    # Агрегируем общие атрибуты по кандидату, сохраняя фасетную группировку.
    agg: dict[str, dict[str, Any]] = {}
    for cid, cname, aid, aname, alabel in shared:
        entry = agg.setdefault(
            cid,
            {"id": cid, "name": cname or cid, "shared_ids": set(), "by_facet": {}},
        )
        if aid in entry["shared_ids"]:
            continue
        entry["shared_ids"].add(aid)
        entry["by_facet"].setdefault(alabel, []).append({"id": aid, "name": aname or aid})

    cand_counts = _cand_attr_counts(store, list(agg), facet_list)
    seed_n = len(seed_ids)

    results: list[dict[str, Any]] = []
    for cid, entry in agg.items():
        inter = len(entry["shared_ids"])
        if inter == 0:
            continue
        cand_n = cand_counts.get(cid, inter)
        union = seed_n + cand_n - inter
        jaccard = inter / union if union > 0 else 0.0
        # overlap — доля атрибутов seed, которые нашлись у кандидата (интуитивнее для UI)
        overlap = inter / seed_n if seed_n else 0.0
        count_by_facet = {f: len(v) for f, v in entry["by_facet"].items()}
        shared_facets = {
            f: sorted(v, key=lambda x: x["name"])[:8] for f, v in entry["by_facet"].items()
        }
        results.append(
            {
                "id": cid,
                "name": entry["name"],
                "similarity": round(jaccard, 4),
                "overlap": round(overlap, 4),
                "shared_count": inter,
                "shared_by_facet": shared_facets,
                "reason": (
                    f"общие: {_facet_label(count_by_facet)}"
                    if count_by_facet
                    else "общие атрибуты"
                ),
            }
        )

    # Ранжируем по Jaccard, ties — по числу общих атрибутов, затем по имени.
    results.sort(
        key=lambda d: (d["similarity"], d["shared_count"], -len(d["name"])), reverse=True
    )
    results = results[: max(1, k)]

    _log.info(
        "similar_materials.similar",
        seed=seed,
        seed_attrs=seed_n,
        candidates=len(agg),
        returned=len(results),
        facets=",".join(facet_list),
    )
    return {
        "seed": {"id": seed, "name": node.get("name") or seed, "label": node.get("label")},
        "facets": facet_list,
        "seed_attributes": [
            {"id": a[0], "name": a[1] or a[0], "label": a[2]} for a in seed_attrs
        ],
        "count": len(results),
        "similar": results,
    }

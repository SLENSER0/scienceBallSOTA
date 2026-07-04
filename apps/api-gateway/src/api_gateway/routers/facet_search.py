"""Фасетный поисковый экран: live-агрегации + фильтр-чипы (§4.7, roadmap #73).

Отдельный browse-режим поверх живого графа (Neo4j, server-профиль :8000). В
`OpenSearch` фасеты считались бы `terms`-агрегациями по keyword-полям
(`material_ids` / `property_ids` / `source_type` / …, §4.6/§4.7). Здесь тот же
контракт реализован над Neo4j: каждый фасет — это `count(*)`-агрегация по
свойству узла, а выдача сужается пересечением выбранных фильтров (та же
set-семантика, что `_passes_filters` в §4.2).

Ключевое поведение фасетного поиска — *drill-down*: счётчики каждого фасета
считаются с учётом фильтров ВСЕХ ОСТАЛЬНЫХ фасетов (но не своего собственного),
поэтому в фасете всегда видно, сколько добавит/уберёт каждое соседнее значение.
Результаты же фильтруются пересечением всех выбранных значений.

Endpoint: ``POST /api/v1/search/faceted``.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1", tags=["search"])

# Фасет-ключ (стабильный API-идентификатор) → свойство узла в графе.
# Набор покрывает quick-filters §5.2.1 / Experiment Explorer §5.2.5: тип узла
# (материал / свойство / лаборатория / …), домен, тип источника, статус ревью,
# география практики и — если поле заполнено при индексации — атмосфера режима.
FACET_FIELDS: dict[str, str] = {
    "type": "label",
    "domain": "domain",
    "source_type": "source_type",
    "review_status": "review_status",
    "practice_type": "practice_type",
    "atmosphere": "atmosphere",
}

# Русские подписи фасетов для UI (бэкенд отдаёт их, чтобы фронт не хардкодил).
FACET_LABELS: dict[str, str] = {
    "type": "Тип",
    "domain": "Домен",
    "source_type": "Источник",
    "review_status": "Статус",
    "practice_type": "Практика",
    "atmosphere": "Атмосфера",
}

# Текстовые поля, по которым матчит свободный запрос (substring, как §4.2 keyword).
_TEXT_FIELDS = ("name", "aliases_text", "canonical_name", "text")

_MAX_LIMIT = 200
_MAX_BUCKETS = 40


class FacetSearchRequest(BaseModel):
    query: str = ""
    # Выбранные значения по каждому фасету: {"type": ["Material"], ...}.
    filters: dict[str, list[str]] = Field(default_factory=dict)
    limit: int = Field(default=30, ge=1, le=_MAX_LIMIT)


def _clean_filters(raw: dict[str, list[str]]) -> dict[str, list[str]]:
    """Оставить только известные фасеты с непустыми списками значений."""
    out: dict[str, list[str]] = {}
    for key, values in (raw or {}).items():
        if key not in FACET_FIELDS or not values:
            continue
        vals = [str(v) for v in values if v is not None and str(v) != ""]
        if vals:
            out[key] = vals
    return out


def _where_clauses(
    query: str,
    filters: dict[str, list[str]],
    exclude: str | None,
    params: dict[str, Any],
) -> list[str]:
    """Собрать WHERE-фрагменты: текст-запрос + все фильтры, кроме ``exclude``.

    ``exclude`` — фасет, счётчики которого сейчас считаем: его собственный фильтр
    не применяется, чтобы drill-down показывал соседние значения фасета.
    """
    clauses: list[str] = []
    q = query.strip().lower()
    if q:
        params["q"] = q
        ors = " OR ".join(f"lower(coalesce(n.{f},'')) CONTAINS $q" for f in _TEXT_FIELDS)
        clauses.append(f"({ors})")
    for key, values in filters.items():
        if key == exclude:
            continue
        prop = FACET_FIELDS[key]
        pname = f"f_{key}"
        params[pname] = values
        clauses.append(f"n.{prop} IN ${pname}")
    return clauses


def _aggregate_facet(store: Any, key: str, query: str, filters: dict[str, list[str]]) -> list[dict]:
    """`terms`-агрегация одного фасета с учётом остальных фильтров (drill-down)."""
    prop = FACET_FIELDS[key]
    params: dict[str, Any] = {}
    clauses = _where_clauses(query, filters, exclude=key, params=params)
    clauses.append(f"n.{prop} IS NOT NULL")
    where = " AND ".join(clauses)
    cypher = (
        f"MATCH (n:Node) WHERE {where} "
        f"RETURN n.{prop} AS v, count(*) AS c ORDER BY c DESC, v ASC LIMIT {_MAX_BUCKETS}"
    )
    rows = store.rows(cypher, params)
    selected = set(filters.get(key, []))
    buckets: list[dict] = []
    for v, c in rows:
        if v is None or str(v) == "":
            continue
        buckets.append({"value": str(v), "count": int(c), "selected": str(v) in selected})
    return buckets


def _fetch_hits(
    store: Any, query: str, filters: dict[str, list[str]], limit: int
) -> tuple[list[dict], int]:
    """Отфильтрованная выдача (пересечение всех фасетов) + общий счётчик."""
    params: dict[str, Any] = {}
    clauses = _where_clauses(query, filters, exclude=None, params=params)
    where = (" AND ".join(clauses)) if clauses else "true"

    total_rows = store.rows(f"MATCH (n:Node) WHERE {where} RETURN count(*)", dict(params))
    total = int(total_rows[0][0]) if total_rows else 0

    cypher = (
        f"MATCH (n:Node) WHERE {where} "
        "RETURN n ORDER BY coalesce(n.confidence, 0.0) DESC, coalesce(n.name, n.id) ASC "
        f"LIMIT {int(limit)}"
    )
    rows = store.rows(cypher, params)
    hits: list[dict] = []
    for r in rows:
        nd = store._node_dict(r[0])
        hits.append(
            {
                "id": nd.get("id"),
                "name": nd.get("name") or nd.get("canonical_name") or nd.get("id"),
                "type": nd.get("label"),
                "domain": nd.get("domain"),
                "source_type": nd.get("source_type"),
                "review_status": nd.get("review_status"),
                "practice_type": nd.get("practice_type"),
                "confidence": nd.get("confidence"),
                "doc_id": nd.get("doc_id"),
                "snippet": (nd.get("text") or "")[:240] or None,
            }
        )
    return hits, total


@router.post("/search/faceted")
def search_faceted(req: FacetSearchRequest) -> dict:
    """Фасетный browse-поиск: живые счётчики фасетов + сужаемая выдача (§4.7).

    Тело: ``{query, filters:{facet:[values]}, limit}``. Ответ:
    ``{query, total, count, hits:[…], facets:{facet:{label, buckets:[{value,
    count, selected}]}}, active_filters, took_ms}``. Счётчики каждого фасета
    учитывают фильтры остальных фасетов (drill-down), выдача — пересечение всех.
    """
    t0 = time.perf_counter()
    store = get_store()
    filters = _clean_filters(req.filters)

    hits, total = _fetch_hits(store, req.query, filters, req.limit)

    facets: dict[str, dict] = {}
    for key in FACET_FIELDS:
        buckets = _aggregate_facet(store, key, req.query, filters)
        if buckets:
            facets[key] = {"label": FACET_LABELS[key], "buckets": buckets}

    return {
        "query": req.query,
        "total": total,
        "count": len(hits),
        "hits": hits,
        "facets": facets,
        "active_filters": filters,
        "took_ms": round((time.perf_counter() - t0) * 1000, 1),
    }

"""§17.11 «Timeline сущности» — эволюция знания о сущности во времени (§5.2.4).

На карточке сущности нужна временная шкала: когда сущность впервые появилась в
корпусе, сколько документов/упоминаний/измерений/доказательств приходится на
каждый год. Показывает, как накапливалось знание о материале/технологии.

Ряд строится напрямую из живого графа (без LLM/сети), реюзая уже существующую
модель ингеста (§5/§6):

* документ несёт `year` (`Document {label:'Document', year}`),
  `HAS_CHUNK` → `Chunk`, `Chunk -[:MENTIONS]-> Entity` — даёт документы/упоминания
  по годам, в которые сущность фигурировала;
* факты/`Evidence` штампуются `source_year` из документа
  (`_doc_geo`, §5.4) — `Evidence -[:FROM_CHUNK]-> Chunk` даёт доказательства по
  годам для любой сущности;
* для материалов `Measurement -[:ABOUT_MATERIAL]-> Material` c `source_year`
  даёт число измерений/экспериментов по годам.

Все запросы — в нормализованном диалекте (`:Node {label}` / `:Rel {type}`),
одинаково работающем на Neo4j (server-профиль) и на embedded Kuzu.

Endpoints (off `/api/v1`, вне graph-роутера `/entities/{id}/neighbors`):

* ``GET /api/v1/entity-timeline/{entity_id}`` — годовой ряд + сводка для ECharts.

Чтение публичное (как остальные read-only entity-эндпоинты); мутаций нет.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/entity-timeline", tags=["entities"])


def _as_year(value: Any) -> int | None:
    """Coerce a stored ``year`` (int | float | numeric str) into a plausible year int."""
    if value is None:
        return None
    try:
        year = int(str(value).strip()[:4]) if isinstance(value, str) else int(value)
    except (ValueError, TypeError):
        return None
    return year if 1800 <= year <= 2100 else None


def _fold(rows: list[list[Any]], bucket: dict[int, dict[str, int]], key: str) -> None:
    """Fold ``[year, count]`` query rows into the per-year ``bucket`` under ``key``."""
    for row in rows:
        year = _as_year(row[0])
        if year is None:
            continue
        count = int(row[1] or 0)
        if count <= 0:
            continue
        bucket.setdefault(year, {})[key] = bucket.setdefault(year, {}).get(key, 0) + count


@router.get("/{entity_id}")
def entity_timeline(entity_id: str, max_years: int = Query(default=80, ge=1, le=400)) -> dict:
    """Годовой ряд появления/упоминаний/измерений/доказательств сущности (§5.2.4).

    404 если сущности нет. Если у сущности нет ни одного датированного источника,
    возвращает пустой ``series`` c нулевой сводкой (валидный 200 — экран рисует
    «нет датированных источников»).
    """
    store = get_store()
    node = store.get_node(entity_id)
    if node is None:
        raise HTTPException(status_code=404, detail="entity not found")

    params = {"id": entity_id}
    # Документы + упоминания по годам: Document -HAS_CHUNK-> Chunk -MENTIONS-> Entity.
    docs = store.rows(
        "MATCH (d:Node {label:'Document'})-[:Rel {type:'HAS_CHUNK'}]->(c:Node)"
        "-[:Rel {type:'MENTIONS'}]->(n:Node {id:$id}) "
        "WHERE d.year IS NOT NULL "
        "RETURN d.year AS year, count(DISTINCT d.id) AS documents, count(c) AS mentions "
        "ORDER BY year",
        params,
    )
    # Доказательства по годам (для любой сущности): Evidence -FROM_CHUNK-> Chunk -MENTIONS-> Entity.
    evidence = store.rows(
        "MATCH (e:Node {label:'Evidence'})-[:Rel {type:'FROM_CHUNK'}]->(c:Node)"
        "-[:Rel {type:'MENTIONS'}]->(n:Node {id:$id}) "
        "WHERE e.source_year IS NOT NULL "
        "RETURN e.source_year AS year, count(DISTINCT e.id) AS evidence "
        "ORDER BY year",
        params,
    )
    # Измерения/эксперименты по годам (материалы): Measurement -ABOUT_MATERIAL-> Entity.
    measurements = store.rows(
        "MATCH (m:Node {label:'Measurement'})-[:Rel {type:'ABOUT_MATERIAL'}]->(n:Node {id:$id}) "
        "WHERE m.source_year IS NOT NULL "
        "RETURN m.source_year AS year, count(DISTINCT m.id) AS measurements "
        "ORDER BY year",
        params,
    )

    bucket: dict[int, dict[str, int]] = {}
    _fold([[r[0], r[1]] for r in docs], bucket, "documents")
    _fold([[r[0], r[2]] for r in docs], bucket, "mentions")
    _fold(evidence, bucket, "evidence")
    _fold(measurements, bucket, "measurements")

    years = sorted(bucket)
    if len(years) > max_years:  # keep the most recent window if the span is huge
        years = years[-max_years:]

    series: list[dict[str, int]] = []
    cum_docs = 0
    for year in years:
        cell = bucket[year]
        cum_docs += cell.get("documents", 0)
        series.append(
            {
                "year": year,
                "documents": cell.get("documents", 0),
                "mentions": cell.get("mentions", 0),
                "measurements": cell.get("measurements", 0),
                "evidence": cell.get("evidence", 0),
                "cumulative_documents": cum_docs,
            }
        )

    summary = {
        "first_seen": years[0] if years else None,
        "last_seen": years[-1] if years else None,
        "span_years": (years[-1] - years[0] + 1) if years else 0,
        "years_covered": len(years),
        "total_documents": sum(p["documents"] for p in series),
        "total_mentions": sum(p["mentions"] for p in series),
        "total_measurements": sum(p["measurements"] for p in series),
        "total_evidence": sum(p["evidence"] for p in series),
    }

    return {
        "entity_id": entity_id,
        "name": node.get("name") or node.get("canonical_name") or entity_id,
        "type": node.get("label"),
        "series": series,
        "summary": summary,
    }

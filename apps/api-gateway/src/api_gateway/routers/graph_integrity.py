"""Панель целостности графа: Cypher-валидатор evidence-first инварианта (§3.6).

Одна ручка доказывает на ВСЁМ корпусе три инварианта §3.6/§3.7 разом:

1. «no source span → no graph fact» — каждый factual-узел (`Measurement`,
   `Claim`, `TechnoEconomicIndicator`, …) обязан иметь минимум один
   `SUPPORTED_BY`/`SUPPORTS`-линк на `:Evidence` (§3.6, критерий приёмки:
   ``MATCH (m:Measurement) WHERE NOT (m)-[:SUPPORTED_BY]->(:Evidence)
   RETURN count(m)`` == 0);
2. каждый узел имеет непустой `id` (детерминированные ID, §3.8);
3. каждый factual-узел несёт `schema_version` (provenance-полнота, §3.7).

Это не новый скоринг, а прямые Cypher-запросы к живому графу через
``store.rows`` — тот же интерфейс, что использует :mod:`api_gateway.
kg_health_metrics` и роутер ``gds_live``. Мы отдаём ещё и сам текст Cypher
каждой проверки, чтобы панель на демо показывала «вот запрос — вот 0 нарушений»
(аргумент доверия: инвариант проверяем, а не декларативен).

Граф в обоих профилях хранится единообразно: узлы под меткой ``:Node`` с
property ``label`` (реальный тип), рёбра ``(:Node)-[:Rel {type}]->(:Node)`` —
поэтому один и тот же Cypher работает и на server (Neo4j), и на embedded (Kuzu).
Ручка только читает граф; ничего не пишет. Префикс ``/graph-integrity`` не
конфликтует с ``/graph`` и ``/admin/kg-health``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api_gateway.deps import get_store
from kg_common import get_logger, get_settings

router = APIRouter(prefix="/api/v1/graph-integrity", tags=["graph-integrity", "admin"])

_log = get_logger("api.graph_integrity")

# Value-bearing («factual») узлы, для которых evidence-first инвариант §3.6
# обязателен: у них должен быть источник (Evidence) и schema_version. Не входят
# resolvable-сущности (Material/Method/…), Evidence и bookkeeping-узлы
# (ExtractorRun/Gap/Contradiction) — они по природе не «факты со значением».
FACTUAL_LABELS: tuple[str, ...] = (
    "Measurement",
    "Claim",
    "TechnoEconomicIndicator",
    "LocalPractice",
    "FactVersion",
)
# Типы рёбер, засчитываемые как привязка к доказательству (§3.6 / §8.2).
EVIDENCE_RELS: tuple[str, ...] = ("SUPPORTED_BY", "SUPPORTS")
_EVIDENCE_LABEL = "Evidence"


def _rows(store: Any, cypher: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
    """Прогнать Cypher на активном store, обернув сбой БД в понятный 503."""
    try:
        return store.rows(cypher, params or {})
    except Exception as exc:  # graph store / driver error
        msg = str(exc)
        _log.warning("graph_integrity.cypher_failed", error=msg[:300])
        raise HTTPException(
            status_code=503,
            detail=f"Не удалось выполнить Cypher-валидатор на графе: {msg[:200]}",
        ) from exc


def _scalar(store: Any, cypher: str, params: dict[str, Any]) -> int:
    rows = _rows(store, cypher, params)
    if not rows or rows[0] is None or rows[0][0] is None:
        return 0
    try:
        return int(rows[0][0])
    except (TypeError, ValueError):
        return 0


def _samples(store: Any, cypher: str, params: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for r in _rows(store, cypher, params):
        nid = "" if not r or r[0] is None else str(r[0])
        label = "" if len(r) < 2 or r[1] is None else str(r[1])
        out.append({"id": nid, "label": label})
    return out


# --- Cypher-валидаторы (текст запроса отдаётся во фронт «как есть») ----------

# Факты без привязки к Evidence: OPTIONAL MATCH + count(e)=0 портируется и на
# Neo4j, и на Kuzu (в отличие от Neo4j-специфичного EXISTS-подзапроса).
_EVIDENCE_BODY = (
    "MATCH (n:Node) WHERE n.label IN $facts\n"
    "OPTIONAL MATCH (n)-[r:Rel]-(e:Node)\n"
    "  WHERE r.type IN $evrels AND e.label = $evlabel\n"
    "WITH n, count(e) AS ev\n"
    "WHERE ev = 0"
)
_ID_BODY = "MATCH (n:Node) WHERE n.id IS NULL OR n.id = ''"
_SCHEMA_BODY = (
    "MATCH (n:Node) WHERE n.label IN $facts\n"
    "  AND (n.schema_version IS NULL OR n.schema_version = '')"
)


def _check(
    store: Any,
    *,
    key: str,
    title: str,
    invariant: str,
    body: str,
    denominator: int,
    sample_limit: int,
) -> dict[str, Any]:
    """Собрать один пункт панели: сколько нарушителей, доля покрытия, примеры."""
    params = {
        "facts": list(FACTUAL_LABELS),
        "evrels": list(EVIDENCE_RELS),
        "evlabel": _EVIDENCE_LABEL,
    }
    violations = _scalar(store, f"{body}\nRETURN count(n) AS c", params)
    samples: list[dict[str, str]] = []
    if violations:
        samples = _samples(
            store,
            f"{body}\nRETURN n.id AS id, n.label AS label LIMIT {int(sample_limit)}",
            params,
        )
    covered = denominator - violations if denominator else 0
    coverage = (covered / denominator) if denominator else 1.0
    # Витринный текст запроса — подставляем конкретные значения вместо $params,
    # чтобы на демо запрос можно было скопировать в Neo4j Browser как есть.
    facts_lit = ", ".join(f"'{lbl}'" for lbl in FACTUAL_LABELS)
    evrels_lit = ", ".join(f"'{rt}'" for rt in EVIDENCE_RELS)
    display = (
        body.replace("$facts", f"[{facts_lit}]")
        .replace("$evrels", f"[{evrels_lit}]")
        .replace("$evlabel", f"'{_EVIDENCE_LABEL}'")
        + "\nRETURN count(n) AS violations"
    )
    return {
        "key": key,
        "title": title,
        "invariant": invariant,
        "denominator": denominator,
        "violations": violations,
        "passed": violations == 0,
        "coverage": round(coverage, 4),
        "cypher": display,
        "samples": samples,
    }


@router.get("/report")
def report(sample_limit: int = Query(default=12, ge=1, le=100)) -> dict[str, Any]:
    """Отчёт целостности графа: «0 фактов без Evidence / без id / без schema_version» (§3.6).

    Прогоняет три Cypher-валидатора на живом графе и возвращает по каждому:
    число нарушителей, долю покрытия, примеры-нарушители и сам текст запроса.
    ``ok=true`` ⇔ все инварианты держатся на всём корпусе — единая метрика
    доверия для демо.
    """
    store = get_store()
    profile = get_settings().runtime_profile

    total_nodes = _scalar(store, "MATCH (n:Node) RETURN count(n) AS c", {})
    total_facts = _scalar(
        store,
        "MATCH (n:Node) WHERE n.label IN $facts RETURN count(n) AS c",
        {"facts": list(FACTUAL_LABELS)},
    )
    total_evidence = _scalar(
        store,
        "MATCH (n:Node) WHERE n.label = $evlabel RETURN count(n) AS c",
        {"evlabel": _EVIDENCE_LABEL},
    )

    checks = [
        _check(
            store,
            key="facts_without_evidence",
            title="Факты без Evidence",
            invariant="каждый факт имеет ≥1 линк SUPPORTED_BY/SUPPORTS → :Evidence (§3.6)",
            body=_EVIDENCE_BODY,
            denominator=total_facts,
            sample_limit=sample_limit,
        ),
        _check(
            store,
            key="nodes_without_id",
            title="Узлы без id",
            invariant="каждый узел несёт непустой детерминированный id (§3.8)",
            body=_ID_BODY,
            denominator=total_nodes,
            sample_limit=sample_limit,
        ),
        _check(
            store,
            key="facts_without_schema_version",
            title="Факты без schema_version",
            invariant="каждый факт несёт schema_version (provenance-полнота §3.7)",
            body=_SCHEMA_BODY,
            denominator=total_facts,
            sample_limit=sample_limit,
        ),
    ]

    total_violations = sum(c["violations"] for c in checks)
    ok = total_violations == 0
    headline = (
        "0 фактов без Evidence, id или schema_version — инвариант держится на всём корпусе"
        if ok
        else f"{total_violations} нарушений инварианта evidence-first на {total_facts} фактах"
    )

    _log.info(
        "graph_integrity.report",
        profile=profile,
        total_facts=total_facts,
        total_violations=total_violations,
        ok=ok,
    )
    return {
        "profile": profile,
        "generated_at": datetime.now(UTC).isoformat(),
        "ok": ok,
        "headline": headline,
        "total_nodes": total_nodes,
        "total_facts": total_facts,
        "total_evidence": total_evidence,
        "total_violations": total_violations,
        "factual_labels": list(FACTUAL_LABELS),
        "evidence_rels": list(EVIDENCE_RELS),
        "checks": checks,
    }

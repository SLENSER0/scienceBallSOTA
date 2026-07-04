"""§18.5 Ops-дашборды: latency p95, throughput, LLM-cost, curation + алерты.

Четыре ЖИВЫХ дашборда наблюдаемости плюс контур алертов — то, что превращает
демо из прототипа в production-платформу. Роутер НЕ пишет собственной числовой
магии сверх необходимого: он переиспользует уже готовые модули —

* :data:`api_gateway.observability.METRICS` — in-process счётчики/латентность по
  route (тот же источник, что и Prometheus-экспозиция ``/api/v1/admin/metrics``);
* :mod:`kg_common.cost` (:func:`cost_for`/:func:`aggregate_costs`/:func:`cost_per_unit`)
  — детерминированный расчёт стоимости LLM по токенам (§18.10);
* граф (:func:`api_gateway.deps.get_store`) — источник правды для curation-событий
  (``CurationEvent`` из :mod:`curation_service`) и для unsupported-claim guardrail
  (числовой ``Measurement`` без ребра ``SUPPORTED_BY`` к ``Evidence``, §16).

Эндпоинты (все под живым server-профилем, Neo4j :8000):

* ``GET /api/v1/ops-dashboards/latency``    — p50/p95/p99 по route + overall, SLO-breaches.
* ``GET /api/v1/ops-dashboards/throughput`` — total/error-rate/RPS + топ маршрутов.
* ``GET /api/v1/ops-dashboards/cost``       — extraction_cost_usd_per_document /
  answer_cost_usd_per_query (оценка токенов по реальному тексту графа).
* ``GET /api/v1/ops-dashboards/curation``   — reviewer_corrections_per_100_extractions,
  разбивка по действию/куратору, свежая лента.
* ``GET /api/v1/ops-dashboards/alerts``     — правила алертов: chat p95 > SLO,
  error-rate > порога, health degraded, **unsupported-claim-rate > 0** (headline).
* ``GET /api/v1/ops-dashboards/overview``   — единая сводка всех четырёх + алертов.
"""

from __future__ import annotations

import re
import time
from typing import Any

from fastapi import APIRouter

from api_gateway.deps import get_store
from api_gateway.observability import METRICS, _percentile

router = APIRouter(prefix="/api/v1/ops-dashboards", tags=["ops-dashboards"])

# Процесс поднялся ~ вместе с приложением; служит знаменателем для RPS.
_STARTED = time.time()

# SLO-пороги (§15.2/§23.9): выше — нарушение бюджета латентности.
SLO_P95_MS: float = 3000.0
CHAT_SLO_P95_MS: float = 8000.0
ERROR_RATE_THRESHOLD: float = 0.05  # доля 5xx-ответов, выше которой алерт

# Представительная цена hosted-модели для расчёта cost-дашборда. Локальный
# OSS-профиль стоит ~0, поэтому дашборд по умолчанию считает по этой ставке,
# чтобы демонстрировать учёт затрат; ставка честно помечена как оценка.
_DEFAULT_INPUT_USD_PER_1K = 0.14
_DEFAULT_OUTPUT_USD_PER_1K = 0.28
_DEFAULT_MODEL_ID = "deepseek-v4-flash"

# Грубая, но детерминированная оценка completion-токенов на один ответ агента —
# типичный связный ответ с цитатами (≈ 350 слов).
_ANSWER_COMPLETION_TOKENS = 470
_ANSWER_PROMPT_OVERHEAD_TOKENS = 900  # system + few-shot + инструкции


# --- helpers ---------------------------------------------------------------


_WORD_RE = re.compile(r"\w+")


def _estimate_tokens(text: str) -> int:
    """Детерминированная оценка токенов = число слов/пунктуаторов реального текста.

    Честный нижний прокси для ``prompt_tokens`` без токенизатора (тот же приём, что
    в :mod:`api_gateway.routers.agent_trace`). Пустой текст даёт 0.
    """
    if not text:
        return 0
    return len(_WORD_RE.findall(text))


def _all_recent_latencies() -> list[float]:
    """Плоский список недавних латентностей по всем route для overall-перцентилей."""
    out: list[float] = []
    for dq in METRICS.latencies.values():
        out.extend(dq)
    return out


def _price():  # type: ignore[no-untyped-def]
    from kg_common.cost import ModelPrice

    return ModelPrice(_DEFAULT_MODEL_ID, _DEFAULT_INPUT_USD_PER_1K, _DEFAULT_OUTPUT_USD_PER_1K)


# --- 1) latency ------------------------------------------------------------


@router.get("/latency")
def latency_dashboard(top: int = 15) -> dict[str, Any]:
    """Latency-дашборд: p50/p95/p99 по route + overall, нарушения SLO (§18.5)."""
    snap = METRICS.snapshot()
    routes = []
    for route, m in snap.items():
        recent = list(METRICS.latencies.get(route, []))
        p99 = _percentile(recent, 99)
        routes.append(
            {
                "route": route,
                "count": m["count"],
                "errors": m["errors"],
                "avg_ms": m["avg_ms"],
                "p50_ms": m["p50_ms"],
                "p95_ms": m["p95_ms"],
                "p99_ms": p99,
                "slo_breach": m["p95_ms"] > SLO_P95_MS,
            }
        )
    routes.sort(key=lambda r: r["p95_ms"], reverse=True)
    overall = _all_recent_latencies()
    breaches = [r for r in routes if r["slo_breach"]]
    return {
        "slo_p95_ms": SLO_P95_MS,
        "overall": {
            "p50_ms": _percentile(overall, 50),
            "p95_ms": _percentile(overall, 95),
            "p99_ms": _percentile(overall, 99),
            "sampled_requests": len(overall),
        },
        "slo_breaches": len(breaches),
        "routes": routes[: max(1, top)],
    }


# --- 2) throughput ---------------------------------------------------------


@router.get("/throughput")
def throughput_dashboard(top: int = 15) -> dict[str, Any]:
    """Throughput-дашборд: суммарный трафик, error-rate, RPS, топ маршрутов (§18.5)."""
    snap = METRICS.snapshot()
    total = sum(m["count"] for m in snap.values())
    errors = sum(m["errors"] for m in snap.values())
    uptime = max(1e-6, time.time() - _STARTED)
    routes = [
        {
            "route": route,
            "count": m["count"],
            "errors": m["errors"],
            "error_rate": round(m["errors"] / m["count"], 4) if m["count"] else 0.0,
            "rps": round(m["count"] / uptime, 4),
        }
        for route, m in snap.items()
    ]
    routes.sort(key=lambda r: r["count"], reverse=True)
    return {
        "uptime_s": round(uptime, 1),
        "total_requests": total,
        "total_errors": errors,
        "error_rate": round(errors / total, 4) if total else 0.0,
        "throughput_rps": round(total / uptime, 4),
        "routes": routes[: max(1, top)],
    }


# --- 3) LLM cost -----------------------------------------------------------


def _document_extraction_costs(store: Any, price: Any, sample: int) -> tuple[list[dict], int]:
    """Оценка extraction-стоимости на документ по реальному тексту его чанков.

    Токены каждого документа = сумма слов его ``Chunk``-текстов; стоимость — по
    входной ставке (extraction = prompt-heavy). Возвращает per-document записи и
    общее число оценённых токенов. Деградирует до пустого списка при ошибке графа.
    """
    from kg_common.cost import cost_for

    prices = {price.model_id: price}
    try:
        rows = store.rows(
            "MATCH (d:Node) WHERE d.label IN ['Document','Paper'] "
            "OPTIONAL MATCH (d)-[e:Rel {type:'HAS_CHUNK'}]->(c:Node {label:'Chunk'}) "
            "RETURN d.id, coalesce(d.name, d.id), "
            "collect(coalesce(c.text, ''))[0..40] "
            "LIMIT $lim",
            {"lim": int(sample)},
        )
    except Exception:
        rows = []
    docs: list[dict] = []
    total_tokens = 0
    for doc_id, name, texts in rows:
        text_list = texts if isinstance(texts, list) else [texts]
        tokens = sum(_estimate_tokens(str(t)) for t in text_list)
        if tokens == 0:
            # нет привязанных чанков — оценим по имени/аннотации документа
            tokens = _estimate_tokens(str(name))
        total_tokens += tokens
        uc = cost_for(price.model_id, tokens, 0, prices)
        docs.append(
            {
                "document_id": str(doc_id),
                "name": str(name)[:120],
                "prompt_tokens": tokens,
                "cost_usd": round(uc.cost_usd, 6),
            }
        )
    docs.sort(key=lambda d: d["cost_usd"], reverse=True)
    return docs, total_tokens


@router.get("/cost")
def cost_dashboard(sample: int = 100, top: int = 15) -> dict[str, Any]:
    """LLM-cost-дашборд: extraction_cost/doc и answer_cost/query (§18.5/§18.10).

    Расчёт детерминированный: токены оцениваются по РЕАЛЬНОМУ тексту графа, а
    стоимость — по представительной hosted-ставке (локальный OSS-профиль ≈ $0).
    """
    from kg_common.cost import aggregate_costs, cost_for, cost_per_unit

    price = _price()
    prices = {price.model_id: price}

    docs, total_tokens = _document_extraction_costs(get_store(), price, sample)
    usages = [
        cost_for(price.model_id, d["prompt_tokens"], 0, prices) for d in docs
    ]
    extraction_agg = aggregate_costs(usages)
    extraction_per_doc = cost_per_unit(usages, len(usages))

    # answer_cost_usd_per_query — представительный ответ агента.
    answer_usage = cost_for(
        price.model_id,
        _ANSWER_PROMPT_OVERHEAD_TOKENS,
        _ANSWER_COMPLETION_TOKENS,
        prices,
    )

    return {
        "model_id": price.model_id,
        "price_usd_per_1k": {
            "input": price.input_usd_per_1k,
            "output": price.output_usd_per_1k,
        },
        "estimate_note": (
            "Токены оценены по реальному тексту графа; ставка — представительная "
            "hosted-цена (локальный OSS-профиль ≈ $0)."
        ),
        "extraction": {
            "documents_sampled": len(docs),
            "total_prompt_tokens": total_tokens,
            "total_cost_usd": extraction_agg["total_usd"],
            "extraction_cost_usd_per_document": round(extraction_per_doc, 6),
            "top_documents": docs[: max(1, top)],
        },
        "answer": {
            "answer_cost_usd_per_query": round(answer_usage.cost_usd, 6),
            "prompt_tokens": answer_usage.prompt_tokens,
            "completion_tokens": answer_usage.completion_tokens,
        },
    }


# --- 4) curation -----------------------------------------------------------


@router.get("/curation")
def curation_dashboard(recent: int = 20) -> dict[str, Any]:
    """Curation-дашборд: reviewer_corrections_per_100_extractions + разбивка (§18.5).

    Источник — ``CurationEvent``-узлы, которые пишет :mod:`curation_service`
    (action/actor/created_at). Знаменатель «на 100 экстракций» — число узлов с
    проставленным ``extractor_run_id`` (реально извлечённые сущности, §10).
    """
    store = get_store()
    by_action: dict[str, int] = {}
    by_actor: dict[str, int] = {}
    recent_events: list[dict] = []
    total_events = 0
    try:
        rows = store.rows(
            "MATCH (e:Node {label:'CurationEvent'}) "
            "RETURN coalesce(e.action,'?'), coalesce(e.actor,'?'), "
            "coalesce(e.created_at,''), coalesce(e.name,'') "
            "ORDER BY e.created_at DESC"
        )
    except Exception:
        rows = []
    for action, actor, created, name in rows:
        total_events += 1
        by_action[str(action)] = by_action.get(str(action), 0) + 1
        by_actor[str(actor)] = by_actor.get(str(actor), 0) + 1
        if len(recent_events) < max(1, recent):
            recent_events.append(
                {
                    "action": str(action),
                    "actor": str(actor),
                    "created_at": str(created),
                    "target": str(name)[:120],
                }
            )

    # знаменатель: реально извлечённые узлы (§10 provenance)
    extractions = 0
    try:
        er = store.rows(
            "MATCH (n:Node) WHERE n.extractor_run_id IS NOT NULL RETURN count(n)"
        )
        extractions = int(er[0][0]) if er else 0
    except Exception:
        extractions = 0

    # «corrections» — правки, меняющие данные (не чистые accept/annotate)
    correction_actions = {"correct", "reject", "merge", "split", "mark_inferred"}
    corrections = sum(v for k, v in by_action.items() if k.lower() in correction_actions)
    per_100 = round(corrections / extractions * 100, 3) if extractions else 0.0

    return {
        "total_events": total_events,
        "corrections": corrections,
        "extractions": extractions,
        "reviewer_corrections_per_100_extractions": per_100,
        "by_action": dict(sorted(by_action.items(), key=lambda kv: kv[1], reverse=True)),
        "by_actor": dict(sorted(by_actor.items(), key=lambda kv: kv[1], reverse=True)),
        "recent": recent_events,
    }


# --- 5) alerts -------------------------------------------------------------


def _unsupported_claim_rate(store: Any) -> dict[str, Any]:
    """Доля числовых claim'ов (``Measurement``) без ребра ``SUPPORTED_BY`` к Evidence.

    Прямой graph-derived сигнал guardrail'а §16 «no numeric claim without
    evidence»: детерминирован и дёшев (без прогона LLM). rate>0 → алерт.
    """
    try:
        rows = store.rows(
            "MATCH (m:Node {label:'Measurement'}) "
            "OPTIONAL MATCH (m)-[e:Rel {type:'SUPPORTED_BY'}]->(ev:Node) "
            "WITH m, count(ev) AS ev_count "
            "RETURN sum(CASE WHEN ev_count=0 THEN 1 ELSE 0 END), count(m)"
        )
        if rows and rows[0][1]:
            unsupported = int(rows[0][0] or 0)
            total = int(rows[0][1])
            return {
                "unsupported": unsupported,
                "total": total,
                "rate": round(unsupported / total, 4) if total else 0.0,
            }
    except Exception:
        pass
    return {"unsupported": 0, "total": 0, "rate": 0.0}


@router.get("/alerts")
def alerts() -> dict[str, Any]:
    """Контур алертов (§18.5): p95 > SLO, error-rate > порога, health degraded,
    **unsupported-claim-rate > 0** (headline, guardrail §16)."""
    store = get_store()
    snap = METRICS.snapshot()
    overall = _all_recent_latencies()
    overall_p95 = _percentile(overall, 95)

    # chat-специфичный p95 (route с '/chat' в пути), иначе overall
    chat_lat = [
        v for route, dq in METRICS.latencies.items() if "/chat" in route for v in dq
    ]
    chat_p95 = _percentile(chat_lat, 95) if chat_lat else overall_p95

    total = sum(m["count"] for m in snap.values())
    err = sum(m["errors"] for m in snap.values())
    error_rate = round(err / total, 4) if total else 0.0

    # health degraded?
    health_ok = True
    try:
        store.rows("MATCH (n:Node) RETURN count(n) LIMIT 1")
    except Exception:
        health_ok = False

    ucr = _unsupported_claim_rate(store)

    rules = [
        {
            "id": "unsupported_claim_rate",
            "title": "Unsupported-claim rate > 0",
            "severity": "critical",
            "value": ucr["rate"],
            "threshold": 0.0,
            "firing": ucr["rate"] > 0.0,
            "detail": f"{ucr['unsupported']}/{ucr['total']} числовых claim без evidence",
        },
        {
            "id": "chat_p95_latency",
            "title": "Chat p95 latency > SLO",
            "severity": "warning",
            "value": chat_p95,
            "threshold": CHAT_SLO_P95_MS,
            "firing": chat_p95 > CHAT_SLO_P95_MS,
            "detail": f"chat p95={chat_p95}ms, SLO={CHAT_SLO_P95_MS}ms",
        },
        {
            "id": "error_rate",
            "title": "Error rate > threshold",
            "severity": "warning",
            "value": error_rate,
            "threshold": ERROR_RATE_THRESHOLD,
            "firing": error_rate > ERROR_RATE_THRESHOLD,
            "detail": f"{err}/{total} запросов вернули 5xx",
        },
        {
            "id": "health_degraded",
            "title": "Health degraded (graph unreachable)",
            "severity": "critical",
            "value": 0 if health_ok else 1,
            "threshold": 0,
            "firing": not health_ok,
            "detail": "graph OK" if health_ok else "graph query failed",
        },
    ]
    firing = [r for r in rules if r["firing"]]
    return {
        "firing_count": len(firing),
        "status": "firing" if firing else "ok",
        "rules": rules,
    }


# --- 6) overview -----------------------------------------------------------


@router.get("/overview")
def overview() -> dict[str, Any]:
    """Единая сводка всех четырёх дашбордов + алертов — один вызов для UI (§18.5)."""
    return {
        "latency": latency_dashboard(top=8),
        "throughput": throughput_dashboard(top=8),
        "cost": cost_dashboard(sample=100, top=8),
        "curation": curation_dashboard(recent=10),
        "alerts": alerts(),
    }

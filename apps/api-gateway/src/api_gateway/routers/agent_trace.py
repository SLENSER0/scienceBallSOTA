"""§18.3 Agent trace viewer — дерево спанов node→tool→LLM + «open trace».

RU: Усиливает готовую agent-transparency (§17.7, `agent_reasoning.py` — плоский
таймлайн) до полноценного **дерева трассировки**: корневой trace → графовые узлы
(§7.5 `intent_classifier`, `entity_resolver`, `query_planner`, `hybrid_retrieval`,
`evidence_verifier`, `gap_analyzer`, `answer_synthesizer`) → tool-спаны (реальные
Cypher-чтения) → LLM-спан синтеза. Каждый спан несёт настоящие `span_id`/`trace_id`
(из `kg_common.tracing`, §18.2), тайминги, статус и доменные атрибуты (`kg.*`,
`tool.*`, `llm.*` — контракт §18.3). Отдаёт ссылку «open trace» для чата: LangSmith
или OTel, если сконфигурированы (`AGENT_TRACING`/`LANGSMITH_API_KEY`/
`OTEL_EXPORTER_OTLP_ENDPOINT`), иначе — внутренний permalink на этот же вьювер.

EN: Builds a **span tree** for one chat question. No rewrite of the agent:

* tool-спаны переиспользуют реальные Cypher-фазы из
  :mod:`api_gateway.routers.agent_reasoning` (`_resolve` / `_graph_query` /
  `_vector_search` / `_evidence_check` / `_gap_scan`, все — живые чтения по
  ``:Node``/``:Rel`` на server-профиле, Neo4j :8000);
* тайминг и graceful-error каждого tool — через
  :func:`agent_service.tool_trace.traced_tool` (§13.23);
* span-/trace-ids — через :func:`kg_common.tracing.root_context` /
  :func:`~kg_common.tracing.child_context` (§18.2, W3C trace-context),
  детерминированно засеяны вопросом (тот же вопрос → тот же trace_id, воспроизводимо);
* интент-заголовок — :func:`agent_service.intent_taxonomy.classify_intent_v2` (§13.8).

Каждый узел графа = отдельный спан (акцептанс §18.3 «каждый node = отдельный
run/span»), под ним tool-/LLM-child-спаны. Плоский ``toolTrace`` в ответе несёт
``spanId`` на каждый шаг — так UI Agent Transparency линкует шаг на спан
(«``tool_trace[i]`` содержит ``span_id``»).

Честность LLM-спана: на server/preview-профиле модель синтеза НЕ вызывается, поэтому
``answer_synthesizer`` помечен ``invoked=false`` — ``llm.model`` берётся из конфигурации,
а ``llm.prompt_tokens``/``completion_tokens`` — детерминированная оценка по реальному
тексту (никаких выдуманных задержек: ``llm.latency_ms`` — измеренное время подготовки).

Endpoint:

* ``POST /api/v1/agent/trace`` — body ``{"question": ...}`` → дерево спанов + «open trace».
"""

from __future__ import annotations

import os
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api_gateway.auth import current_user
from api_gateway.deps import get_store
from kg_common import get_settings
from kg_common.tracing import child_context, new_span_id, root_context, span_id_from

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])

# --------------------------------------------------------------------------- #
# §7.5 graph-node plan → the tool each node runs. Order is the orchestrator's  #
# evidence-first sequence. Each node becomes a span; its `phase` names the real #
# Cypher fn reused from agent_reasoning, its `tool` the §7.4 registry name the  #
# UI shows, and `kind` marks the leaf span type (tool vs llm).                  #
# --------------------------------------------------------------------------- #
# (node, tool, phase, kind, human label)
_PLAN: tuple[tuple[str, str, str, str, str], ...] = (
    ("intent_classifier", "classify_intent", "intent", "tool", "intent classification"),
    ("entity_resolver", "resolve_entities", "resolve", "tool", "resolved entities"),
    ("query_planner", "run_cypher_template", "graph_query", "tool", "graph query"),
    ("hybrid_retrieval", "hybrid_search", "vector_search", "tool", "hybrid retrieval"),
    ("evidence_verifier", "get_evidence_by_ids", "evidence_check", "tool", "evidence check"),
    ("gap_analyzer", "scan_gaps", "gap_scan", "tool", "gap scan"),
    ("answer_synthesizer", "synthesize", "synthesize", "llm", "answer synthesis"),
)

# Short human rationale per graph node — «что делает узел» for the expandable span.
_NODE_RATIONALE: dict[str, str] = {
    "intent_classifier": "Классифицирует научный интент вопроса (§13.8) — выбирает план tools.",
    "entity_resolver": "Сопоставляет упоминания из вопроса с каноническими сущностями графа.",
    "query_planner": "Обходит связи графа знаний вокруг найденных сущностей (Cypher-шаблоны).",
    "hybrid_retrieval": "Гибридный ретрив фактов по тексту узлов (лексический слой на server).",
    "evidence_verifier": "Собирает доказательства (SUPPORTED_BY → Evidence) под найденные факты.",
    "gap_analyzer": "Ищет открытые пробелы (Gap ABOUT темы) вокруг вопроса.",
    "answer_synthesizer": "Синтезирует ответ из фактов и доказательств (LLM, evidence-first).",
}

# status → icon key, reused vocabulary from tool_timeline.STATUS_ICONS (§17.7).
_STATUS_ICON: dict[str, str] = {"ok": "done", "error": "error"}

_WORD_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)

# Cap on ids threaded into downstream IN-clauses (keeps Cypher params sane).
_ID_CAP = 40


class TraceBody(BaseModel):
    """POST /trace payload — вопрос пользователя / the user's question."""

    question: str


def _estimate_tokens(text: str) -> int:
    """Deterministic token estimate: real word/punct count of ``text`` (не выдумка).

    A whitespace-and-punctuation split over the *actual* prompt/answer text — an
    honest lower-bound proxy for ``llm.prompt_tokens`` when no tokenizer/model is
    invoked on the server profile (§18.3 `llm.*`).
    """
    return len(_WORD_RE.findall(text or ""))


def _icon(status: str) -> str:
    """Map a span status to the §17.7 icon key (unknown → pending)."""
    return _STATUS_ICON.get(status, "pending")


# --------------------------------------------------------------------------- #
# Tracing config → «open trace» provider + link (§18.3 AGENT_TRACING switch).  #
# --------------------------------------------------------------------------- #
def _tracing_config() -> dict[str, Any]:
    """Resolve the agent-tracing provider from env/settings (langsmith|otel|both|off)."""
    settings = get_settings()
    langsmith_key = ""
    try:  # SecretStr → str, tolerant of config surface changes
        langsmith_key = settings.langsmith_api_key.get_secret_value()
    except Exception:
        langsmith_key = os.getenv("LANGSMITH_API_KEY", "")
    otel_endpoint = getattr(settings, "otel_endpoint", "") or os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", ""
    )
    project = os.getenv("LANGCHAIN_PROJECT", "science-ball")
    mode = os.getenv("AGENT_TRACING", "").strip().lower()
    langsmith_on = bool(langsmith_key) and mode in ("", "langsmith", "both")
    otel_on = bool(otel_endpoint) and mode in ("", "otel", "both")
    return {
        "agentTracing": mode or "auto",
        "langsmithConfigured": langsmith_on,
        "otelConfigured": otel_on,
        "project": project,
        "otelEndpoint": otel_endpoint,
    }


def _open_trace(trace_id: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Build the «open trace» descriptor the chat button uses (§18.3 open trace).

    Prefers LangSmith, then OTel (when configured), else an internal permalink back to
    this viewer keyed by ``trace_id`` — the internal link always works so the button is
    never dead (акцептанс «во фронтенде работает open trace»).
    """
    if cfg["langsmithConfigured"]:
        project = cfg["project"]
        url = (
            f"https://smith.langchain.com/projects/p/{project}"
            f"?searchModel=%7B%22filter%22%3A%22and(eq(metadata_key%2C%5C%22trace_id%5C%22)"
            f"%2Ceq(metadata_value%2C%5C%22{trace_id}%5C%22))%22%7D"
        )
        return {"provider": "langsmith", "url": url, "label": "Open in LangSmith",
                "external": True}
    if cfg["otelConfigured"]:
        return {"provider": "otel", "url": cfg["otelEndpoint"], "label": "Open in trace backend",
                "external": True}
    return {
        "provider": "internal",
        "url": f"?view=agenttrace&trace={trace_id}",
        "label": "Открыть трейс",
        "external": False,
    }


# --------------------------------------------------------------------------- #
# Phase execution — reuses agent_reasoning's real Cypher reads (no rewrite).   #
# --------------------------------------------------------------------------- #
def _phase_summary(phase: str, result: dict[str, Any] | None, intent: Any) -> str:
    """One short human line per executed phase (used as the span summary)."""
    if phase == "intent":
        return (
            f"интент: {intent.intent.value} · {intent.confidence * 100:.0f}%"
            if intent is not None
            else "интент не определён"
        )
    if result is None:
        return "шаг завершился ошибкой / step failed"
    if phase == "resolve":
        return f"сопоставлено сущностей: {len(result.get('entities', []))}"
    if phase == "graph_query":
        return (
            f"соседей: {len(result.get('neighbors', []))}, "
            f"типов связей: {len(result.get('relationTypes', {}))}"
        )
    if phase == "vector_search":
        return f"релевантных фактов: {len(result.get('hits', []))}"
    if phase == "evidence_check":
        return (
            f"доказательств: {len(result.get('evidence', []))} "
            f"на {result.get('factCount', 0)} факт(ов)"
        )
    if phase == "gap_scan":
        return f"открытых пробелов: {len(result.get('gaps', []))}"
    return phase


def _run_tree(store: Any, question: str) -> dict[str, Any]:
    """Execute the §7.5 node plan live and assemble the node→tool→LLM span tree."""
    from agent_service.intent_taxonomy import classify_intent_v2
    from agent_service.tool_trace import traced_tool

    from api_gateway.routers.agent_reasoning import (
        _evidence_check,
        _gap_scan,
        _graph_query,
        _resolve,
        _tokens,
        _vector_search,
    )

    # Deterministic root context seeded by the question → reproducible trace_id (§18.2).
    root = root_context(seed=f"agent-trace/{question}")
    trace_id = root.trace_id

    # Best-effort intent header (§13.8) — drives the plan story, never fatal.
    try:
        intent = classify_intent_v2(question)
    except Exception:
        intent = None

    tokens = _tokens(question)
    clock = lambda: time.perf_counter() * 1000.0  # ms clock  # noqa: E731
    t0 = clock()

    # Each phase's real Cypher fn, bound so `traced_tool(name, fn, args, clock)` runs it.
    def _phase_fn(phase: str, entity_ids: list[str], scope_ids: list[str]) -> Any:
        if phase == "intent":
            return lambda _a: (
                {"intent": intent.intent.value, "confidence": intent.confidence,
                 "matched": list(intent.matched)}
                if intent is not None
                else {"intent": None}
            )
        if phase == "resolve":
            return lambda a: _resolve(store, a["tokens"])
        if phase == "graph_query":
            return lambda a: _graph_query(store, a["ids"])
        if phase == "vector_search":
            return lambda a: _vector_search(store, a["tokens"])
        if phase == "evidence_check":
            return lambda a: _evidence_check(store, a["ids"])
        if phase == "gap_scan":
            return lambda a: _gap_scan(store, a["ids"])
        return lambda _a: {}

    def _phase_args(phase: str, entity_ids: list[str], scope_ids: list[str]) -> dict[str, Any]:
        if phase in ("resolve", "vector_search"):
            return {"tokens": tokens}
        if phase == "graph_query":
            return {"ids": entity_ids}
        if phase in ("evidence_check", "gap_scan"):
            return {"ids": scope_ids}
        return {}

    nodes: list[dict[str, Any]] = []
    flat_trace: list[dict[str, Any]] = []
    entity_ids: list[str] = []
    scope_ids: list[str] = []
    tool_count = 0
    llm_count = 0

    for node_name, tool_name, phase, kind, label in _PLAN:
        # -- node span (parent) --------------------------------------------
        node_span = child_context(root, span_id_from(f"{trace_id}/{node_name}"))
        node_start = clock()

        child: dict[str, Any]
        if kind == "llm":
            # answer_synthesizer: model NOT invoked on server/preview — honest estimate.
            llm_count += 1
            settings = get_settings()
            model = getattr(settings, "llm_model_synth", "deepseek/deepseek-v4-flash")
            prompt_txt = f"{question}\n" + " ".join(tokens)
            prompt_tokens = _estimate_tokens(prompt_txt)
            finished = clock()
            latency = round(finished - node_start, 1)
            child = {
                "spanId": new_span_id(seed=f"{trace_id}/{node_name}/llm"),
                "parentSpanId": node_span.span_id,
                "traceId": trace_id,
                "kind": "llm",
                "node": node_name,
                "name": tool_name,
                "label": label,
                "status": "ok",
                "iconKey": "done",
                "offsetMs": round(node_start - t0, 1),
                "durationMs": latency,
                "summary": f"модель: {model} (оценка токенов по тексту; не вызывается на preview)",
                "error": None,
                "attributes": {
                    "llm.model": model,
                    "llm.provider": "openrouter",
                    "llm.prompt_tokens": prompt_tokens,
                    "llm.completion_tokens": 0,
                    "llm.latency_ms": latency,
                    "llm.invoked": False,
                    "llm.note": "server/preview profile — synthesis model not called; "
                    "tokens estimated from real prompt text (§18.3).",
                },
                "detail": {"prompt_preview": prompt_txt[:200]},
                "children": [],
            }
        else:
            # real tool span via traced_tool (timing + graceful error, §13.23).
            fn = _phase_fn(phase, entity_ids, scope_ids)
            args = _phase_args(phase, entity_ids, scope_ids)
            result, entry = traced_tool(tool_name, fn, args, clock)
            tool_count += 1
            status = entry.status
            result_size = _result_size(result)
            child = {
                "spanId": new_span_id(seed=f"{trace_id}/{node_name}/tool"),
                "parentSpanId": node_span.span_id,
                "traceId": trace_id,
                "kind": "tool",
                "node": node_name,
                "name": tool_name,
                "label": label,
                "status": status,
                "iconKey": _icon(status),
                "offsetMs": round(entry.started_at - t0, 1),
                "durationMs": round(entry.finished_at - entry.started_at, 1),
                "summary": _phase_summary(phase, result, intent),
                "error": entry.error,
                "attributes": {
                    "tool.name": tool_name,
                    "tool.latency_ms": round(entry.finished_at - entry.started_at, 1),
                    "tool.status": status,
                    "tool.result_size": result_size,
                },
                "detail": result if result is not None else {"error": entry.error},
                "children": [],
            }
            # Thread ids forward exactly as agent_reasoning does.
            if phase == "resolve":
                entity_ids = [
                    e["id"] for e in (result or {}).get("entities", []) if e.get("id")
                ][:_ID_CAP]
                scope_ids = list(entity_ids)
            elif phase == "graph_query":
                related = [
                    n["id"] for n in (result or {}).get("neighbors", []) if n.get("id")
                ]
                scope_ids = list(dict.fromkeys([*entity_ids, *related]))[:_ID_CAP]

        node_end = clock()

        # -- node span attributes (kg.* domain, §18.2) ---------------------
        node_attrs: dict[str, Any] = {"kg.node": node_name}
        if intent is not None:
            node_attrs["kg.intent"] = intent.intent.value
        if phase == "resolve":
            node_attrs["kg.entity_count"] = len((child["detail"] or {}).get("entities", []))
        elif phase == "vector_search":
            node_attrs["kg.retrieval_mode"] = "hybrid_lexical"
        elif phase == "evidence_check":
            node_attrs["kg.evidence_count"] = len((child["detail"] or {}).get("evidence", []))

        node_dict = {
            "spanId": node_span.span_id,
            "parentSpanId": root.span_id,
            "traceId": trace_id,
            "kind": "node",
            "node": node_name,
            "name": node_name,
            "label": label,
            "status": child["status"],
            "iconKey": child["iconKey"],
            "offsetMs": round(node_start - t0, 1),
            "durationMs": round(node_end - node_start, 1),
            "summary": child["summary"],
            "rationale": _NODE_RATIONALE.get(node_name, ""),
            "attributes": node_attrs,
            "children": [child],
        }
        nodes.append(node_dict)

        # Flat trace row carries spanId so UI can link a step → span (§18.3 tool_trace).
        flat_trace.append(
            {
                "stepIndex": len(flat_trace),
                "node": node_name,
                "tool": tool_name,
                "kind": kind,
                "spanId": child["spanId"],
                "parentSpanId": node_span.span_id,
                "traceId": trace_id,
                "status": child["status"],
                "iconKey": child["iconKey"],
                "durationMs": child["durationMs"],
                "summary": child["summary"],
            }
        )

    total = round(clock() - t0, 1)
    cfg = _tracing_config()

    return {
        "question": question,
        "traceId": trace_id,
        "rootSpanId": root.span_id,
        "traceparent": root.to_header(),
        "intent": (
            {"intent": intent.intent.value, "confidence": intent.confidence,
             "matched": list(intent.matched)}
            if intent is not None
            else None
        ),
        "tokens": tokens,
        "totalDurationMs": total,
        "spanCount": 1 + len(nodes) + tool_count + llm_count,
        "nodeCount": len(nodes),
        "toolCount": tool_count,
        "llmCount": llm_count,
        "statusCounts": _status_counts(flat_trace),
        "tree": nodes,
        "toolTrace": flat_trace,
        "tracingConfig": cfg,
        "openTrace": _open_trace(trace_id, cfg),
    }


def _result_size(result: Any) -> int:
    """Rough result size for `tool.result_size` — element count of the payload."""
    if result is None:
        return 0
    if isinstance(result, dict):
        total = 0
        for v in result.values():
            total += len(v) if isinstance(v, (list, tuple, dict)) else 1
        return total
    if isinstance(result, (list, tuple)):
        return len(result)
    return 1


def _status_counts(flat_trace: list[dict[str, Any]]) -> dict[str, int]:
    """Tally leaf-span statuses across the flat trace."""
    counts: dict[str, int] = {}
    for row in flat_trace:
        st = str(row.get("status", ""))
        counts[st] = counts.get(st, 0) + 1
    return counts


@router.post("/trace")
def agent_trace(body: TraceBody, user: str = Depends(current_user)) -> dict:
    """Run the live §18.3 span tree for a question and return node→tool→LLM + open-trace.

    The response carries the ``traceId``/``rootSpanId`` (real W3C ids, §18.2), the
    classified ``intent`` header, the ``tree`` (graph nodes, each with a child tool/LLM
    span carrying real timings, status and ``kg.*``/``tool.*``/``llm.*`` attributes), a
    flat ``toolTrace`` where every step carries its ``spanId`` (so the chat can link a
    step to its span), the resolved ``tracingConfig`` and the ``openTrace`` descriptor
    (LangSmith/OTel link when configured, else an internal permalink to this viewer).
    """
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="question is required")
    return _run_tree(get_store(), question)

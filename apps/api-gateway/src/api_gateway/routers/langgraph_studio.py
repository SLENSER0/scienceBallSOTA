"""§19.10 LangGraph Studio — граф ``scientific_agent`` + live node-trace.

RU: Отдаёт две вещи, ради которых существует Studio, но без внешнего сервиса —
прямо во фронте платформы:

* **Топология графа агента** «как в Studio»: реальный скомпилированный
  ``StateGraph`` (``agent_service.agent.build_agent`` → ``.get_graph()``) со своим
  каноничным ``draw_mermaid`` от самого LangGraph, плюс канонический §7.2-контур
  из :mod:`agent_service.graph_topology` (12 узлов §7.5 + START/END, все рёбра
  §7.2, включая retry-петлю verifier→query_planner и ROUTE-fan-out). Оба описания
  честны: compiled — это то, что реально исполняется, canonical — спецификация,
  на соответствие которой compiled проверяется (``validate_topology``).
* **Live node-trace**: реальный прогон §18.3-дерева спанов
  (:func:`api_gateway.routers.agent_trace._run_tree`, живые Cypher-чтения по
  ``:Node``/``:Rel`` на server-профиле, Neo4j :8000) переложенный на узлы графа —
  для каждого узла: исполнялся ли, порядок, статус, тайминг, краткое резюме. Фронт
  подсвечивает активный путь по диаграмме и вешает бейджи длительности — тот самый
  «trace viewer» из Studio, только на нашем графе и наших данных.

Ничего не переписываем: топология — из готового ``graph_topology.py``, live-трасса
— из готового ``agent_trace._run_tree`` (§18.3), langgraph-mermaid — от самого
LangGraph. Роутер только собирает их в Studio-подобный ответ.

Endpoints (prefix ``/api/v1/agent/studio``):

* ``GET  /graph``            — топология ``scientific_agent`` (compiled + canonical
  + langgraph.json-дескриптор + оба mermaid).
* ``POST /trace``           — body ``{"question": ...}`` → live node-trace,
  разложенный по узлам графа (+ активный путь, тайминги, open-trace).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api_gateway.auth import current_user
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/agent/studio", tags=["agent"])

# Имя графа как в langgraph.json (§19.10: graphs: scientific_agent → build_graph).
GRAPH_ID = "scientific_agent"

# Псевдо-узлы LangGraph → человекочитаемый ярлык; помечаем терминалы.
_START = "__start__"
_END = "__end__"

# §7.5 узлы графа → короткое «что делает узел» (для Studio-подписей).
_NODE_RATIONALE: dict[str, str] = {
    "preprocess_question": "Нормализует вопрос: язык, единицы, синонимы (§7.5).",
    "intent_classifier": "Классифицирует научный интент — выбирает план retrieval-веток.",
    "entity_resolver": "Сопоставляет упоминания с каноническими сущностями графа.",
    "query_planner": "ROUTE-планировщик: раздаёт задачу по веткам извлечения (§7.2).",
    "structured_retrieval": "Структурный обход графа знаний (Cypher-шаблоны).",
    "hybrid_retrieval": "Гибридный ретрив фактов по тексту узлов (лексический слой).",
    "graphrag_search": "GraphRAG-поиск по локальным/глобальным сообществам.",
    "gap_analyzer": "Ищет открытые пробелы (Gap ABOUT темы) вокруг вопроса.",
    "evidence_assembler": "Собирает доказательства (SUPPORTED_BY → Evidence) под факты.",
    "verifier": "Проверяет цитаты по реальным узлам; при провале — retry к планировщику.",
    "answer_synthesizer": "Синтезирует ответ из фактов и доказательств (LLM, evidence-first).",
    "visualization_payload": "Формирует graph-payload для canvas/визуализации ответа.",
}

# Алиасы между именами узлов live-трассы (§18.3 `_PLAN`) и каноничными §7.2-узлами.
# Live-план короче (7 узлов) — маппим на канонический контур, чтобы подсветить путь.
_TRACE_TO_CANONICAL: dict[str, str] = {
    "intent_classifier": "intent_classifier",
    "entity_resolver": "entity_resolver",
    "query_planner": "query_planner",
    "hybrid_retrieval": "hybrid_retrieval",
    "evidence_verifier": "verifier",
    "gap_analyzer": "gap_analyzer",
    "answer_synthesizer": "answer_synthesizer",
}


def _pretty(node_id: str) -> str:
    """Человекочитаемый ярлык узла (терминалы → START/END, иначе Title Case)."""
    if node_id == _START:
        return "START"
    if node_id == _END:
        return "END"
    return node_id.replace("_", " ").strip().title()


# --------------------------------------------------------------------------- #
# Compiled StateGraph → Studio-топология (то, что реально исполняется).        #
# --------------------------------------------------------------------------- #
def _compiled_topology(store: Any) -> dict[str, Any] | None:
    """Извлечь топологию из скомпилированного ``StateGraph`` LangGraph.

    Использует собственный ``get_graph()``/``draw_mermaid()`` LangGraph — ровно то,
    что рисует Studio. При недоступности langgraph/agent (graceful) → ``None``.
    """
    try:
        from agent_service.agent import get_agent

        compiled = get_agent(store)
        drawable = compiled.get_graph()
    except Exception:
        return None

    nodes: list[dict[str, Any]] = []
    for node in drawable.nodes.values():
        nid = node.id
        nodes.append(
            {
                "id": nid,
                "label": _pretty(nid),
                "isStart": nid == _START,
                "isEnd": nid == _END,
            }
        )

    edges: list[dict[str, Any]] = []
    for edge in drawable.edges:
        edges.append(
            {
                "source": edge.source,
                "target": edge.target,
                "conditional": bool(getattr(edge, "conditional", False)),
            }
        )

    mermaid = ""
    try:
        mermaid = drawable.draw_mermaid()
    except Exception:
        mermaid = ""

    real_nodes = [n for n in nodes if not n["isStart"] and not n["isEnd"]]
    return {
        "source": "langgraph.compiled",
        "nodes": nodes,
        "edges": edges,
        "mermaid": mermaid,
        "nodeCount": len(real_nodes),
        "edgeCount": len(edges),
    }


# --------------------------------------------------------------------------- #
# Canonical §7.2 topology (спецификация — из готового graph_topology.py).      #
# --------------------------------------------------------------------------- #
def _canonical_topology() -> dict[str, Any]:
    """Канонический §7.2-контур из :mod:`agent_service.graph_topology` (12 узлов)."""
    from agent_service.graph_topology import (
        RETRIEVAL_BRANCHES,
        build_agent_graph,
        draw_mermaid,
        validate_topology,
    )

    g = build_agent_graph()
    branch_set = set(RETRIEVAL_BRANCHES)

    nodes: list[dict[str, Any]] = []
    for nid in g.nodes:
        is_start = nid == "START"
        is_end = nid == "END"
        nodes.append(
            {
                "id": nid,
                "label": _pretty(nid) if not (is_start or is_end) else nid,
                "isStart": is_start,
                "isEnd": is_end,
                "isRetrievalBranch": nid in branch_set,
                "rationale": _NODE_RATIONALE.get(nid, ""),
            }
        )

    edges = [{"source": a, "target": b} for a, b in g.edges]
    real_nodes = [n for n in nodes if not n["isStart"] and not n["isEnd"]]
    return {
        "source": "graph_topology.canonical",
        "nodes": nodes,
        "edges": edges,
        "mermaid": draw_mermaid(g),
        "retrievalBranches": list(RETRIEVAL_BRANCHES),
        "nodeCount": len(real_nodes),
        "edgeCount": len(edges),
        "topologyIssues": validate_topology(g),
    }


def _assistant_descriptor(compiled: dict[str, Any] | None) -> dict[str, Any]:
    """``langgraph.json``-подобный дескриптор ассистента (§19.10 graphs-маппинг)."""
    return {
        "graphId": GRAPH_ID,
        # Маппинг graphs как в langgraph.json: id → путь к билдеру графа (§19.10).
        "entrypoint": "agent_service.agent:build_agent",
        "checkpointer": "postgres",  # §7.3: thread/state persist через checkpointer.
        "compiledAvailable": compiled is not None,
        "runtime": "in-process LangGraph (server profile, Neo4j :8000)",
    }


# --------------------------------------------------------------------------- #
# GET /graph — топология scientific_agent.                                    #
# --------------------------------------------------------------------------- #
@router.get("/graph")
def studio_graph(user: str = Depends(current_user)) -> dict:
    """Топология графа ``scientific_agent`` в стиле LangGraph Studio.

    Возвращает ``compiled`` (реальный ``StateGraph.get_graph()`` + langgraph-mermaid,
    то что исполняется), ``canonical`` (§7.2-спецификация из ``graph_topology`` с
    ROUTE-fan-out, retry-петлёй и проверкой топологии) и ``assistant``-дескриптор
    (langgraph.json-маппинг ``scientific_agent`` → билдер графа).
    """
    store = get_store()
    compiled = _compiled_topology(store)
    canonical = _canonical_topology()
    return {
        "graphId": GRAPH_ID,
        "assistant": _assistant_descriptor(compiled),
        "compiled": compiled,
        "canonical": canonical,
    }


# --------------------------------------------------------------------------- #
# POST /trace — live node-trace, разложенный по узлам графа.                   #
# --------------------------------------------------------------------------- #
class TraceBody(BaseModel):
    """POST /trace payload — вопрос пользователя / the user's question."""

    question: str


def _node_trace(canonical: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    """Разложить live-трассу (§18.3 ``_run_tree``) по каноническим узлам графа.

    Для каждого исполненного узла live-плана берём его канонический алиас и
    статус/тайминг/резюме; неисполненные узлы графа помечаем ``executed=false``.
    Возвращает per-node overlay + упорядоченный активный путь.
    """
    # node -> live span-инфо (первый исполненный спан узла).
    executed: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for node_span in run.get("tree", []):
        canon = _TRACE_TO_CANONICAL.get(node_span.get("node", ""))
        if not canon or canon in executed:
            continue
        executed[canon] = node_span
        order.append(canon)

    overlay: list[dict[str, Any]] = []
    for node in canonical["nodes"]:
        nid = node["id"]
        span = executed.get(nid)
        if span is not None:
            overlay.append(
                {
                    "node": nid,
                    "label": node.get("label", nid),
                    "executed": True,
                    "order": order.index(nid),
                    "status": span.get("status", "ok"),
                    "iconKey": span.get("iconKey", "done"),
                    "offsetMs": span.get("offsetMs", 0.0),
                    "durationMs": span.get("durationMs", 0.0),
                    "summary": span.get("summary", ""),
                    "spanId": span.get("spanId"),
                }
            )
        else:
            overlay.append(
                {
                    "node": nid,
                    "label": node.get("label", nid),
                    "executed": False,
                    "order": None,
                    "status": "skipped" if not (node["isStart"] or node["isEnd"]) else "n/a",
                    "iconKey": "pending",
                    "offsetMs": None,
                    "durationMs": None,
                    "summary": node.get("rationale", ""),
                    "spanId": None,
                }
            )

    # Активный путь START → …executed… → END (для подсветки на диаграмме).
    active_path = ["START", *order, "END"]
    return {
        "overlay": overlay,
        "executedPath": active_path,
        "executedNodes": order,
        "executedCount": len(order),
    }


@router.post("/trace")
def studio_trace(body: TraceBody, user: str = Depends(current_user)) -> dict:
    """Live node-trace для вопроса, разложенный по узлам графа ``scientific_agent``.

    Реально прогоняет §18.3-дерево спанов (живые Cypher-чтения по графу) и
    перекладывает его на канонический §7.2-контур: активный путь, per-node статус и
    тайминг, счётчики, open-trace. Фронт подсвечивает исполненные узлы по диаграмме.
    """
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="question is required")

    from api_gateway.routers.agent_trace import _run_tree

    store = get_store()
    run = _run_tree(store, question)
    canonical = _canonical_topology()
    trace = _node_trace(canonical, run)

    return {
        "graphId": GRAPH_ID,
        "question": question,
        "traceId": run.get("traceId"),
        "intent": run.get("intent"),
        "totalDurationMs": run.get("totalDurationMs"),
        "spanCount": run.get("spanCount"),
        "statusCounts": run.get("statusCounts"),
        "canonical": canonical,
        "nodeTrace": trace,
        "toolTrace": run.get("toolTrace", []),
        "openTrace": run.get("openTrace"),
    }

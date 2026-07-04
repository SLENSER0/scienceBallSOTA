"""Agent tool-call timeline endpoint (§17.7 «Agent transparency», SOTA #7).

Surfaces *how the scientific agent thinks* for a given question as an ordered,
labelled timeline of the tool phases it will run — ``resolved entities → graph
query → vector search → evidence check → gap scan`` (§5.2.2). This is the "agent
transparency" wow-surface for the chat: before/while the answer streams, the UI can
show the planned reasoning steps and their status.

The timeline is **real, not fabricated**: it reuses the agent's own decision logic —
the §13.8 named-intent classifier (:func:`agent_service.intent_taxonomy.classify_intent_v2`)
and the §13.10 deterministic tool planner (:func:`agent_service.tool_planner.plan_tools`).
For a question the classifier picks one of the nine §7.5 intents (with the matched
signals that explain *why*), and the planner returns the exact, evidence-first tool
sequence the §7.5 orchestrator runs for that intent. Each planned tool is mapped to
one of the five canonical §5.2.2 UI stages so the icons/labels stay consistent
regardless of the raw tool name in the stream (§17.7 acceptance).

Endpoint:

* ``POST /api/v1/agent/timeline`` — body ``{"question": ...}`` → the planned timeline
  (``intent`` + ``confidence`` + ``matched`` signals + ordered ``steps``).

Pure and deterministic (no store, no LLM, no clock), so it is instant and live-safe
under the Neo4j server profile; the same question always yields the same timeline.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api_gateway.auth import current_user

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


# -- §5.2.2 canonical UI stages -------------------------------------------------
# The five stages the chat timeline draws, in fixed left-to-right order. Every
# planned tool maps onto exactly one of these so icons/labels are consistent
# regardless of the raw tool name (§17.7 «сопоставить лейблы … с реальными tools»).
STAGES: tuple[tuple[str, str], ...] = (
    ("resolve", "resolved entities"),
    ("graph", "graph query"),
    ("vector", "vector search"),
    ("evidence", "evidence check"),
    ("gap", "gap scan"),
)
STAGE_LABEL: dict[str, str] = dict(STAGES)

# Raw planner/§7.4 tool name → canonical stage id. Covers both the §13.6 focused
# planner names (graph_search / evidence_lookup / gap_check / global_search / …) and
# the §7.4 named-tool registry (run_cypher_template / hybrid_search / …), so the same
# mapping works whether the plan or a live tool_trace drives the timeline.
TOOL_STAGE: dict[str, str] = {
    # resolve
    "resolve_entities": "resolve",
    "search_material_aliases": "resolve",
    # graph query (structured / Cypher / neighbourhood)
    "graph_search": "graph",
    "run_cypher_template": "graph",
    "run_cypher_readonly": "graph",
    "find_graph_paths": "graph",
    "expand_subgraph": "graph",
    "get_experiment_table": "graph",
    "compare_practice": "graph",
    "graph_schema": "graph",
    # vector / semantic + keyword + numeric filter (Mode A/B/C retrieval)
    "hybrid_search": "vector",
    "vector_search_qdrant": "vector",
    "keyword_search_opensearch": "vector",
    "global_search": "vector",
    "numeric_filter": "vector",
    # evidence check (provenance / snippets)
    "evidence_lookup": "evidence",
    "get_evidence_by_ids": "evidence",
    "get_document_snippet": "evidence",
    # gap / contradiction scan
    "gap_check": "gap",
    "scan_gaps": "gap",
    "detect_contradictions": "gap",
    "create_review_task": "gap",
}

# Short human rationale per stage — «what this phase does» for the expandable step.
STAGE_RATIONALE: dict[str, str] = {
    "resolve": "Сопоставляет упоминания в вопросе с каноническими сущностями графа "
    "(материалы, свойства, режимы).",
    "graph": "Обходит граф знаний по структурным связям (Cypher-шаблоны, соседи, пути).",
    "vector": "Семантический + ключевой поиск по чанкам источников (RRF-слияние).",
    "evidence": "Собирает доказательства и сниппеты источников под каждое утверждение "
    "(evidence-first).",
    "gap": "Проверяет пробелы в данных и противоречия по найденным фактам.",
}


class TimelineBody(BaseModel):
    """POST /timeline payload — вопрос пользователя / the user's question."""

    question: str


def _plan_timeline(question: str) -> dict:
    """Build the §5.2.2 tool timeline for ``question`` from the agent's own logic.

    Reuses :func:`classify_intent_v2` (§13.8) and :func:`plan_tools` (§13.10) — no
    rewrite of the agent — then maps each planned tool to its canonical stage.
    """
    from agent_service.intent_taxonomy import classify_intent_v2
    from agent_service.tool_planner import plan_tools

    intent = classify_intent_v2(question)
    plan = plan_tools(intent.intent, question)

    steps: list[dict] = []
    for i, tool in enumerate(plan.steps):
        stage = TOOL_STAGE.get(tool, "graph")
        steps.append(
            {
                "stepIndex": i,
                "tool": tool,
                "stage": stage,
                "label": STAGE_LABEL[stage],
                "rationale": STAGE_RATIONALE[stage],
                # planned == not yet executed; the UI animates pending→running→done,
                # or overlays a live tool_trace status when one is available (§17.7).
                "status": "planned",
            }
        )

    return {
        "question": question,
        "intent": intent.intent.value,
        "confidence": intent.confidence,
        "matched": list(intent.matched),
        "parallel": plan.parallel,
        # canonical stage legend (id + label), fixed order, for the UI legend/rail.
        "stages": [{"id": sid, "label": label} for sid, label in STAGES],
        "steps": steps,
    }


@router.post("/timeline")
def agent_timeline(body: TimelineBody, user: str = Depends(current_user)) -> dict:
    """Return the planned tool-call timeline (§5.2.2) for a question (§17.7).

    The response carries the classified ``intent`` (+ ``confidence`` and the matched
    signals that explain it) and the ordered ``steps`` — each a planned agent tool
    mapped to one of the five §5.2.2 stages with a human ``label`` and ``rationale``.
    """
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="question is required")
    return _plan_timeline(question)

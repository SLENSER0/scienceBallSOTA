"""LangGraph agent (§13): parse → retrieve → access-filter → synthesize.

A compiled StateGraph per graph store. Returns an ``AnswerPayload`` with grounded
markdown, citations, a graph payload, comparison table, gaps, contradictions and
a confidence score.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agent_service.access import apply_access_policy
from agent_service.synthesize import build_answer
from kg_common import AnswerPayload, get_logger
from kg_extractors.query_parser import parse_query
from kg_retrievers.graph_retriever import GraphRetriever
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("agent")


class AgentState(TypedDict, total=False):
    query: str
    role: str
    use_llm: bool
    intent: Any
    retrieval: Any
    answer: AnswerPayload


def build_agent(store: KuzuGraphStore):  # type: ignore[no-untyped-def]
    retriever = GraphRetriever(store)

    def n_parse(state: AgentState) -> dict[str, Any]:
        intent = parse_query(state["query"])
        _log.info(
            "agent.parsed",
            entities=len(intent.entities),
            type=intent.query_type,
            constraints=len(intent.numeric_constraints),
        )
        return {"intent": intent}

    def n_retrieve(state: AgentState) -> dict[str, Any]:
        retrieval = retriever.retrieve(state["intent"])
        # Hybrid fallback (§12): add corpus passages when a search index exists.
        hybrid = _get_hybrid()
        if hybrid is not None and hybrid.available():
            for hit in hybrid.search(state["intent"].raw, limit=5):
                retrieval.passages.append(
                    {
                        "text": hit.payload.get("text", ""),
                        "doc_id": hit.payload.get("doc_id"),
                        "page": hit.payload.get("page"),
                        "score": round(hit.score, 4),
                    }
                )
        retrieval = apply_access_policy(retrieval, state.get("role", "researcher"))
        return {"retrieval": retrieval}

    def n_synthesize(state: AgentState) -> dict[str, Any]:
        answer = build_answer(
            state["intent"], state["retrieval"], use_llm=state.get("use_llm", True)
        )
        return {"answer": answer}

    def n_verify(state: AgentState) -> dict[str, Any]:
        # §13.16: ground citations against real nodes, cap confidence if ungrounded
        from agent_service.verifier import apply_verification

        return {"answer": apply_verification(store, state["answer"])}

    g: StateGraph = StateGraph(AgentState)
    g.add_node("parse", n_parse)
    g.add_node("retrieve", n_retrieve)
    g.add_node("synthesize", n_synthesize)
    g.add_node("verify", n_verify)
    g.add_edge(START, "parse")
    g.add_edge("parse", "retrieve")
    g.add_edge("retrieve", "synthesize")
    g.add_edge("synthesize", "verify")
    g.add_edge("verify", END)
    return g.compile()


_hybrid_cache: list[Any] = []


def _get_hybrid():  # type: ignore[no-untyped-def]
    """Lazily open the on-disk hybrid stores; None if unavailable (graceful)."""
    if not _hybrid_cache:
        try:
            from kg_retrievers.hybrid import HybridRetriever

            _hybrid_cache.append(HybridRetriever.open_default())
        except Exception:
            _hybrid_cache.append(None)
    return _hybrid_cache[0]


_agents: dict[str, Any] = {}


def get_agent(store: KuzuGraphStore):  # type: ignore[no-untyped-def]
    key = store.db_path
    if key not in _agents:
        _agents[key] = build_agent(store)
    return _agents[key]


def answer_query(
    query: str, store: KuzuGraphStore, *, role: str = "researcher", use_llm: bool = True
) -> AnswerPayload:
    agent = get_agent(store)
    out = agent.invoke({"query": query, "role": role, "use_llm": use_llm})
    return out["answer"]

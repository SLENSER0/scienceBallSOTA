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
    geography: str  # explicit практика filter: russia | cis | foreign | global | all
    preprocess: dict[str, Any]
    intent: Any
    intent_class: dict[str, Any]
    retrieval: Any
    answer: AnswerPayload


def build_agent(store: KuzuGraphStore):  # type: ignore[no-untyped-def]
    retriever = GraphRetriever(store)

    def n_preprocess(state: AgentState) -> dict[str, Any]:
        # §13.7 Node 1: language detect + unicode/whitespace normalization + intent flags
        from agent_service.preprocess import preprocess_query

        pp = preprocess_query(state["query"])
        return {"query": pp.text, "preprocess": pp.as_dict()}

    def n_parse(state: AgentState) -> dict[str, Any]:
        from agent_service.intent_classifier import classify_intent

        intent = parse_query(state["query"])
        # Explicit UI geography filter overrides whatever the text implied (§ гео-фильтр).
        geo = state.get("geography")
        if geo and geo != "all":
            intent.practice_types = [geo]
        ic = classify_intent(state["query"])  # §13.8 explicit intent + routing
        _log.info(
            "agent.parsed",
            entities=len(intent.entities),
            type=intent.query_type,
            intent_class=ic.query_type,
            constraints=len(intent.numeric_constraints),
        )
        return {"intent": intent, "intent_class": ic.as_dict()}

    def n_retrieve(state: AgentState) -> dict[str, Any]:
        retrieval = retriever.retrieve(state["intent"])
        # §13.13: thematic/global questions also map-reduce community summaries
        if (state.get("intent_class") or {}).get("query_type") == "global":
            try:
                from kg_retrievers.community_search import global_search

                ga = global_search(store, state["query"], limit=3)
                for c in ga.communities:
                    retrieval.passages.append({"text": c.summary, "score": round(c.score, 4)})
            except Exception:  # global enrichment is best-effort
                pass
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
            state["intent"],
            state["retrieval"],
            use_llm=state.get("use_llm", True),
            reasoning_mode=state.get("reasoning_mode", False),
        )
        return {"answer": answer}

    def n_verify(state: AgentState) -> dict[str, Any]:
        # §13.16: ground citations against real nodes, cap confidence if ungrounded
        from agent_service.verifier import apply_verification

        return {"answer": apply_verification(store, state["answer"])}

    g: StateGraph = StateGraph(AgentState)
    g.add_node("preprocess", n_preprocess)
    g.add_node("parse", n_parse)
    g.add_node("retrieve", n_retrieve)
    g.add_node("synthesize", n_synthesize)
    g.add_node("verify", n_verify)
    g.add_edge(START, "preprocess")
    g.add_edge("preprocess", "parse")
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
            from kg_retrievers.retrieval_factory import make_hybrid_retriever

            _hybrid_cache.append(make_hybrid_retriever())
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
    query: str,
    store: KuzuGraphStore,
    *,
    role: str = "researcher",
    use_llm: bool = True,
    geography: str | None = None,
) -> AnswerPayload:
    agent = get_agent(store)
    state: dict[str, Any] = {"query": query, "role": role, "use_llm": use_llm}
    if geography:
        state["geography"] = geography
    out = agent.invoke(state)
    return out["answer"]


def answer_query_stream(
    query: str,
    store: KuzuGraphStore,
    *,
    role: str = "researcher",
    geography: str | None = None,
):
    """Streaming variant of :func:`answer_query`.

    Runs the same preprocess → parse → retrieve steps, then delegates to
    :func:`synthesize.stream_answer`, yielding ('meta', obj) → ('token', str)* →
    ('final', dict) so the UI shows a brief conclusion in seconds and streams the rest.
    """
    from agent_service.intent_classifier import classify_intent
    from agent_service.preprocess import preprocess_query
    from agent_service.synthesize import stream_answer

    retriever = GraphRetriever(store)
    pp = preprocess_query(query)
    intent = parse_query(pp.text)
    if geography and geography != "all":
        intent.practice_types = [geography]
    ic = classify_intent(pp.text)
    retrieval = retriever.retrieve(intent)
    if ic.as_dict().get("query_type") == "global":
        try:
            from kg_retrievers.community_search import global_search

            ga = global_search(store, pp.text, limit=3)
            for c in ga.communities:
                retrieval.passages.append({"text": c.summary, "score": round(c.score, 4)})
        except Exception:  # global enrichment is best-effort
            pass
    hybrid = _get_hybrid()
    if hybrid is not None and hybrid.available():
        for hit in hybrid.search(intent.raw, limit=5):
            retrieval.passages.append(
                {
                    "text": hit.payload.get("text", ""),
                    "doc_id": hit.payload.get("doc_id"),
                    "page": hit.payload.get("page"),
                    "score": round(hit.score, 4),
                }
            )
    retrieval = apply_access_policy(retrieval, role)
    yield from stream_answer(intent, retrieval)

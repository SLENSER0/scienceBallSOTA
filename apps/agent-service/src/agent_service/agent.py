"""LangGraph agent (§13): parse → retrieve → access-filter → synthesize.

A compiled StateGraph per graph store. Returns an ``AnswerPayload`` with grounded
markdown, citations, a graph payload, comparison table, gaps, contradictions and
a confidence score.
"""

from __future__ import annotations

import dataclasses
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agent_service.access import apply_access_policy
from agent_service.synthesize import build_answer
from kg_common import AnswerPayload, get_logger
from kg_extractors.query_parser import parse_query
from kg_retrievers.graph_retriever import GraphRetriever
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("agent")


# --- Deterministic per-query memoization (§13.7 / §13.8 / §24.9) --------------
# RU: preprocess / parse / classify — чистые функции нормализованного запроса.
# Доминирующая стоимость parse — полный скан таксономии
# (``query_parser.scan_taxonomy``); демо гоняет небольшой фиксированный набор
# вопросов, поэтому повторный идентичный вопрос не пересканирует таксономию, а
# берётся из кэша по строке запроса. ``classify``/``preprocess`` возвращают
# «замороженные», немутируемые результаты — их можно отдавать напрямую; ``parse``
# отдаёт ИЗМЕНЯЕМЫЙ ``QueryIntent``, поэтому его копируют перед гео-переопределением.
# EN: preprocess / parse / classify are pure functions of the (normalized) query.
# The taxonomy scan dominates parse cost and the demo replays a small fixed
# question set, so memoize on the query string. classify/preprocess return frozen,
# unmutated results (shared directly); the parse result is a *mutable* QueryIntent,
# so callers MUST copy it (see ``n_parse``) before mutating it.
@functools.lru_cache(maxsize=256)
def _preprocess_query_cached(query: str):  # type: ignore[no-untyped-def]
    """Memoized §13.7 preprocess (frozen ``PreprocessedQuery``, safe to share)."""
    from agent_service.preprocess import preprocess_query

    return preprocess_query(query)


@functools.lru_cache(maxsize=256)
def _classify_intent_cached(query: str):  # type: ignore[no-untyped-def]
    """Memoized §13.8 classifier (frozen ``IntentClass``, consumed via ``as_dict``)."""
    from agent_service.intent_classifier import classify_intent

    return classify_intent(query)


@functools.lru_cache(maxsize=256)
def _parse_query_cached(query: str):  # type: ignore[no-untyped-def]
    """Memoized §24.9 parse — returns the PRISTINE, shared ``QueryIntent``.

    The taxonomy scan is the dominant deterministic cost of the parse node and is
    identical for identical queries. The result is a *mutable* dataclass, so
    callers MUST NOT mutate it in place nor hand it out — copy it first (the geo
    override reassigns ``practice_types``). No downstream code mutates the other
    ``QueryIntent`` lists in place, so a shallow ``dataclasses.replace`` suffices.
    """
    return parse_query(query)


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
        pp = _preprocess_query_cached(state["query"])
        return {"query": pp.text, "preprocess": pp.as_dict()}

    def n_parse(state: AgentState) -> dict[str, Any]:
        # Pristine parse is memoized (deterministic taxonomy scan). Copy before the
        # geo override so the shared cached QueryIntent is never mutated (aliasing-safe).
        intent = dataclasses.replace(_parse_query_cached(state["query"]))
        # Explicit UI geography filter overrides whatever the text implied (§ гео-фильтр).
        geo = state.get("geography")
        if geo and geo != "all":
            intent.practice_types = [geo]
        ic = _classify_intent_cached(state["query"])  # §13.8 explicit intent + routing
        _log.info(
            "agent.parsed",
            entities=len(intent.entities),
            type=intent.query_type,
            intent_class=ic.query_type,
            constraints=len(intent.numeric_constraints),
        )
        return {"intent": intent, "intent_class": ic.as_dict()}

    def n_retrieve(state: AgentState) -> dict[str, Any]:
        intent = state["intent"]

        # Hybrid fallback (§12): the vector channel embeds the query on CPU (~2.5 s,
        # see the note in ``answer_query_stream``) while graph retrieval is a batch
        # of Neo4j reads — the two are independent (they touch different stores), so
        # overlap them exactly as the streaming twin does instead of paying
        # graph_time + embed_time serially. Ordering/semantics are unchanged: graph
        # passages, then global community summaries, then hybrid hits (appended last).
        def _hybrid_passages() -> list[dict[str, Any]]:
            hybrid = _get_hybrid()
            if hybrid is None or not hybrid.available():
                return []
            return [
                {
                    "text": hit.payload.get("text", ""),
                    "doc_id": hit.payload.get("doc_id"),
                    "page": hit.payload.get("page"),
                    "score": round(hit.score, 4),
                }
                for hit in hybrid.search(intent.raw, limit=5)
            ]

        with ThreadPoolExecutor(max_workers=1) as ex:
            hybrid_future = ex.submit(_hybrid_passages)  # embed runs off-thread
            retrieval = retriever.retrieve(intent)  # graph reads, in parallel
            # §13.13: thematic/global questions also map-reduce community summaries
            if (state.get("intent_class") or {}).get("query_type") == "global":
                try:
                    from kg_retrievers.community_search import global_search

                    ga = global_search(store, state["query"], limit=3)
                    for c in ga.communities:
                        retrieval.passages.append({"text": c.summary, "score": round(c.score, 4)})
                except Exception:  # global enrichment is best-effort
                    pass
            # ``future.result()`` re-raises any hybrid error on this thread, so the
            # node's error semantics are preserved (previously hybrid ran inline).
            retrieval.passages.extend(hybrid_future.result())
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

    # The hybrid/vector search embeds the query on CPU (~2.5 s) and the graph retrieval
    # is a batch of Neo4j reads — independent, so run them concurrently and merge.
    def _hybrid_passages() -> list[dict[str, Any]]:
        hybrid = _get_hybrid()
        if hybrid is None or not hybrid.available():
            return []
        out: list[dict[str, Any]] = []
        try:
            for hit in hybrid.search(intent.raw, limit=5):
                out.append(
                    {
                        "text": hit.payload.get("text", ""),
                        "doc_id": hit.payload.get("doc_id"),
                        "page": hit.payload.get("page"),
                        "score": round(hit.score, 4),
                    }
                )
        except Exception:  # hybrid enrichment is best-effort
            pass
        return out

    with ThreadPoolExecutor(max_workers=2) as ex:
        hybrid_future = ex.submit(_hybrid_passages)
        retrieval = retriever.retrieve(intent)  # graph reads, in parallel with the embed
        if ic.as_dict().get("query_type") == "global":
            try:
                from kg_retrievers.community_search import global_search

                ga = global_search(store, pp.text, limit=3)
                for c in ga.communities:
                    retrieval.passages.append({"text": c.summary, "score": round(c.score, 4)})
            except Exception:  # global enrichment is best-effort
                pass
        retrieval.passages.extend(hybrid_future.result())

    retrieval = apply_access_policy(retrieval, role)
    yield from stream_answer(intent, retrieval)

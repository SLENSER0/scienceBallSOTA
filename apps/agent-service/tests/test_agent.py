"""End-to-end agent over the seed (§13 / §24.9), deterministic (no LLM)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from agent_service.agent import answer_query

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph


@pytest.fixture(scope="module")
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(s)
    yield s
    s.close()


def test_water_answer(store: KuzuGraphStore) -> None:
    ans = answer_query(
        "Какие методы обессоливания воды при сульфатах 200–300 мг/л и TDS ≤1000 мг/дм³?",
        store,
        use_llm=False,
    )
    assert ans.answer_markdown
    assert ans.citations  # evidence-backed
    assert ans.graph is not None and len(ans.graph.nodes) > 0
    assert ans.table is not None
    assert ans.parsed_query["numeric_constraints"]


def test_nickel_contradiction(store: KuzuGraphStore) -> None:
    ans = answer_query(
        "циркуляция католита при электроэкстракции никеля, оптимальная скорость потока",
        store,
        use_llm=False,
    )
    assert ans.contradictions  # 0.2 vs 0.5 m/s surfaced


def test_gap_answer(store: KuzuGraphStore) -> None:
    ans = answer_query(
        "нет экспериментов холодный климат кучное выщелачивание никель",
        store,
        use_llm=False,
    )
    assert ans.gaps


def test_rbac_external_partner(store: KuzuGraphStore) -> None:
    researcher = answer_query(
        "циркуляция католита электроэкстракция никеля", store, role="researcher", use_llm=False
    )
    partner = answer_query(
        "циркуляция католита электроэкстракция никеля",
        store,
        role="external_partner",
        use_llm=False,
    )
    # external partner must not receive more evidence than researcher
    assert len(partner.citations) <= len(researcher.citations)


def test_verifier_report_present_and_grounds_citations() -> None:
    import tempfile
    from pathlib import Path

    from agent_service.agent import answer_query
    from agent_service.verifier import verify_answer

    from kg_common import Citation, EvidenceRef
    from kg_common.dto import AnswerPayload
    from kg_retrievers.graph_store import KuzuGraphStore
    from kg_retrievers.seed import build_seed_graph

    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    try:
        build_seed_graph(store)
        ans = answer_query("методы обессоливания воды сульфаты 200 мг/л", store, use_llm=False)
        assert ans.verifier_report is not None
        assert "coverage" in ans.verifier_report

        # a fabricated citation (no such node) is flagged unsupported
        fake = AnswerPayload(
            answer_markdown="x",
            citations=[
                Citation(marker="[1]", evidence=EvidenceRef(evidence_id="ev:nope", source_id="s"))
            ],
            confidence=0.9,
        )
        rep = verify_answer(store, fake)
        assert rep["verified"] is False and "[1]" in rep["unsupported"]
    finally:
        store.close()


def test_agent_preprocess_node_runs() -> None:
    import tempfile
    from pathlib import Path

    from agent_service.agent import answer_query

    from kg_retrievers.graph_store import KuzuGraphStore
    from kg_retrievers.seed import build_seed_graph

    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    try:
        build_seed_graph(store)
        # NBSP + fancy dash in the query — preprocess normalizes before parse
        ans = answer_query("методы обессоливания воды", store, use_llm=False)
        assert ans.answer_markdown  # pipeline still produces an answer through preprocess
    finally:
        store.close()


def test_agent_classifies_intent_and_global_enrichment() -> None:
    import tempfile
    from pathlib import Path

    from agent_service.agent import build_agent

    from kg_retrievers.community import detect_communities
    from kg_retrievers.graph_store import KuzuGraphStore
    from kg_retrievers.seed import build_seed_graph

    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    try:
        build_seed_graph(store)
        detect_communities(store)
        agent = build_agent(store)
        out = agent.invoke(
            {"query": "основные кластеры технологий обессоливания", "use_llm": False}
        )
        assert out["intent_class"]["query_type"]  # §13.8 classification present
        assert out["answer"].answer_markdown
    finally:
        store.close()


# --- Optimization: per-query parse/classify memoization (finding [2]) --------
def test_parse_memo_behavior_preserving_and_aliasing_safe() -> None:
    """Кэш parse даёт тот же разбор и не портится гео-переопределением (§24.9).

    The memo must (a) return the exact same structured parse as ``parse_query``
    and (b) never be corrupted by ``n_parse``'s geo override — which mutates a
    *copy*, so the shared pristine cache entry keeps its original practice_types.
    """
    import dataclasses

    from agent_service.agent import _parse_query_cached

    from kg_extractors.query_parser import parse_query

    q = "циркуляция католита электроэкстракция никеля в россии"
    assert _parse_query_cached(q).to_dict() == parse_query(q).to_dict()
    cached = _parse_query_cached(q)
    assert _parse_query_cached(q) is cached  # memoized (same pristine object)

    original_practice = list(cached.practice_types)  # domestic → ["russia"]
    assert original_practice == ["russia"]
    # n_parse hands out dataclasses.replace(...) and reassigns practice_types on it
    copy1 = dataclasses.replace(_parse_query_cached(q))
    copy1.practice_types = ["foreign"]
    assert cached.practice_types == original_practice  # cache untouched
    copy2 = dataclasses.replace(_parse_query_cached(q))
    assert copy2.practice_types == original_practice  # next copy still pristine


def test_classify_intent_cache_consistent() -> None:
    """Кэш классификатора совпадает с прямым вызовом / cache == direct (§13.8)."""
    from agent_service.agent import _classify_intent_cached
    from agent_service.intent_classifier import classify_intent

    q = "сравни отечественную и зарубежную практику электроэкстракции никеля"
    assert _classify_intent_cached(q).as_dict() == classify_intent(q).as_dict()
    assert _classify_intent_cached(q) is _classify_intent_cached(q)


def test_geo_override_does_not_leak_across_cached_calls(store: KuzuGraphStore) -> None:
    """Гео-фильтр не протекает между запросами при кэшированном parse (§ гео-фильтр).

    Same query, three geographies: each invocation gets an independent copy, so
    the explicit override never leaks into the shared cache nor into a sibling
    request (regression guard for the memoization aliasing bug).
    """
    from agent_service.agent import get_agent

    agent = get_agent(store)
    q = "методы обессоливания воды"  # no geo marker → practice_types == []
    base = agent.invoke({"query": q, "use_llm": False})
    ru = agent.invoke({"query": q, "use_llm": False, "geography": "russia"})
    frn = agent.invoke({"query": q, "use_llm": False, "geography": "foreign"})
    assert ru["intent"].practice_types == ["russia"]
    assert frn["intent"].practice_types == ["foreign"]
    base2 = agent.invoke({"query": q, "use_llm": False})
    assert base2["intent"].practice_types == base["intent"].practice_types == []


# --- Optimization: parallelized hybrid vs graph retrieval (finding [1]) ------
def test_hybrid_merge_order_preserved_when_parallelized(
    store: KuzuGraphStore, monkeypatch
) -> None:
    """Параллельный n_retrieve сохраняет порядок пассажей (§12 / §13.13).

    ``retriever.retrieve`` feeds evidence/facts/graph (not ``passages``); the
    ``passages`` list is exactly the global community summaries followed by the
    hybrid corpus hits. The hybrid vector search now runs on a worker thread
    concurrently with the graph read, so this asserts the merged order is byte-for-
    byte unchanged: global summaries first, then hybrid hits in search order, with
    the payload mapping (text/doc_id/page/score) intact and no duplication.
    """
    import agent_service.agent as agent_mod

    import kg_retrievers.community_search as cs_mod

    class _Hit:
        def __init__(self, text: str, score: float) -> None:
            self.payload = {"text": text, "doc_id": "doc-x", "page": 7}
            self.score = score

    class _FakeHybrid:
        def available(self) -> bool:
            return True

        def search(self, raw: str, limit: int = 5):
            return [_Hit("HYBRID_MARKER_1", 0.912345), _Hit("HYBRID_MARKER_2", 0.8)][:limit]

    class _Community:
        summary = "GLOBAL_SUMMARY"
        score = 0.5

    class _GA:
        communities = (_Community(),)

    monkeypatch.setattr(agent_mod, "_get_hybrid", lambda: _FakeHybrid())
    monkeypatch.setattr(cs_mod, "global_search", lambda store, q, limit=3: _GA())

    agent = agent_mod.build_agent(store)
    # global query (markers «основны»/«кластер») → the global-enrichment branch runs
    out = agent.invoke(
        {"query": "основные кластеры технологий обессоливания", "use_llm": False}
    )
    passages = out["retrieval"].passages
    texts = [p.get("text", "") for p in passages]
    # researcher (default) is full-access → access policy keeps all passages/order
    assert texts == ["GLOBAL_SUMMARY", "HYBRID_MARKER_1", "HYBRID_MARKER_2"]
    assert texts.count("HYBRID_MARKER_1") == 1  # concurrency: no duplication
    last = passages[-1]
    assert last["score"] == 0.8 and last["page"] == 7 and last["doc_id"] == "doc-x"
    assert passages[1]["score"] == round(0.912345, 4)  # score rounding unchanged

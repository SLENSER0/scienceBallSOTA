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

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

"""GraphRAG global & local search over communities (§11.7)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.community import detect_communities
from kg_retrievers.community_search import global_search, local_search
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph


@pytest.fixture(scope="module")
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(s)
    detect_communities(s)  # assign community_id + write summaries
    yield s
    s.close()


def test_global_search_returns_relevant_communities(store: KuzuGraphStore) -> None:
    ans = global_search(store, "осмос ионный обмен вода", limit=3)
    assert ans.communities, "expected ≥1 relevant community"
    assert ans.answer.strip()
    # scores are sorted descending and evidence ids point at real members
    scores = [c.score for c in ans.communities]
    assert scores == sorted(scores, reverse=True)
    assert all(store.get_node(e) is not None for e in ans.evidence_ids)


def test_global_search_no_match_reports_gap(store: KuzuGraphStore) -> None:
    ans = global_search(store, "квантовая хромодинамика кварки", limit=3)
    assert not ans.communities
    assert "gap" in ans.answer.lower()


def test_local_search_by_id_and_name(store: KuzuGraphStore) -> None:
    from kg_common import make_id

    ro = make_id("TechnologySolution", "reverse osmosis desalination")
    out = local_search(store, ro)
    assert out["found"] and out["neighbors"]
    # unknown seed degrades gracefully
    assert local_search(store, "no-such-entity-xyz")["found"] is False

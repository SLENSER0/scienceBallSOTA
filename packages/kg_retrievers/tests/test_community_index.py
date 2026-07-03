"""Inverted index over community summaries for global search (§11.5)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.community import detect_communities
from kg_retrievers.community_index import CommunityIndex
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph


@pytest.fixture(scope="module")
def index() -> CommunityIndex:
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(s)
    detect_communities(s)  # write Finding community-summary nodes + assign community_id
    idx = CommunityIndex.build_from_store(s)
    s.close()
    return idx


def test_build_indexes_at_least_one_community(index: CommunityIndex) -> None:
    stats = index.as_dict()
    assert stats["communities"] >= 1
    assert stats["tokens"] >= 1
    # every posting points at a real, summarized community
    for cids in index.postings.values():
        assert all(cid in index.summaries for cid in cids)


def test_search_osmos_voda_returns_ranked_community(index: CommunityIndex) -> None:
    hits = index.search("осмос вода", limit=5)
    assert hits, "expected ≥1 community for the water-desalination query"
    top_cid, top_score = hits[0]
    # both query tokens land in one water-treatment community → full overlap
    assert top_score == pytest.approx(1.0)
    # the winning community's summary is about reverse osmosis + water
    summary = index.summary_for(top_cid).lower()
    assert "осмос" in summary or "вода" in summary


def test_unknown_query_returns_empty(index: CommunityIndex) -> None:
    assert index.search("квантовая хромодинамика кварки") == []
    assert index.search("") == []  # empty query is not an error


def test_summary_for_returns_text(index: CommunityIndex) -> None:
    top_cid = index.search("осмос вода")[0][0]
    text = index.summary_for(top_cid)
    assert isinstance(text, str) and text.strip()
    assert index.summary_for(10_000) == ""  # unknown community → empty, no raise


def test_scores_are_descending(index: CommunityIndex) -> None:
    # spans two domains (water + electrometallurgy) so ≥2 communities score
    hits = index.search("осмос вода никель католит", limit=5)
    assert len(hits) >= 2
    scores = [score for _, score in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 < score <= 1.0 for score in scores)


def test_empty_store_is_graceful() -> None:
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))  # schema created, no nodes
    idx = CommunityIndex.build_from_store(s)
    s.close()
    assert idx.as_dict() == {"communities": 0, "tokens": 0}
    assert idx.search("осмос вода") == []
    assert idx.summary_for(0) == ""

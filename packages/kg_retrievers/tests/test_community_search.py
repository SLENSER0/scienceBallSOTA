"""GraphRAG global & local search over communities (§11.7)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.community import detect_communities
from kg_retrievers.community_search import (
    CommunityHit,
    _all_members_named,
    _ensure_summaries,
    _members_named,
    _tokens,
    global_search,
    local_search,
)
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


# --- behaviour-preservation for the grouped-member-scan optimisation ---------


def test_all_members_named_matches_per_community_scan(store: KuzuGraphStore) -> None:
    """One grouped scan == C per-community scans (ids, order, searchable text)."""
    grouped = _all_members_named(store)
    for s in _ensure_summaries(store):
        cid = int(s["community_id"])
        old = _members_named(store, cid)  # [(id, searchable_text), ...]
        new = grouped.get(cid, [])  # [(id, name, searchable_text), ...]
        assert [m[0] for m in new] == [o[0] for o in old], f"member ids/order differ @cid={cid}"
        assert [m[2] for m in new] == [o[1] for o in old], f"searchable text differs @cid={cid}"
        # the grouped name field reproduces the old get_node fallback: `name or id`
        for mid, nm, _ in new:
            assert (nm or mid) == (store.get_node(mid) or {}).get("name", mid)


def _old_global_communities(store: KuzuGraphStore, query: str, *, limit: int) -> list[CommunityHit]:
    """Reference implementation of the pre-optimisation global_search inner loop."""
    q = _tokens(query)
    scored: list[CommunityHit] = []
    for s in _ensure_summaries(store):
        cid = int(s["community_id"])
        text = s.get("summary") or ""
        named = _members_named(store, cid)
        searchable = _tokens(text) | {t for _, nm in named for t in _tokens(nm)}
        overlap = len(q & searchable)
        if overlap == 0:
            continue
        member_ids = [mid for mid, _ in named]
        names = [(store.get_node(m) or {}).get("name", m) for m in member_ids[:8]]
        scored.append(
            CommunityHit(
                community_id=cid,
                score=overlap / (len(q) or 1),
                summary=text,
                top_entities=names,
                member_ids=member_ids,
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:limit]


@pytest.mark.parametrize(
    "query",
    [
        "осмос ионный обмен вода",
        "квантовая хромодинамика кварки",  # no-match branch
        "мембрана фильтрация металл",
    ],
)
def test_global_search_equals_old_per_community_algorithm(
    store: KuzuGraphStore, query: str
) -> None:
    """New grouped-scan global_search returns byte-identical hits to the old loop."""
    expected = _old_global_communities(store, query, limit=3)
    got = global_search(store, query, limit=3)
    assert [c.__dict__ for c in got.communities] == [c.__dict__ for c in expected]
    assert got.evidence_ids == [m for c in expected for m in c.member_ids[:5]]

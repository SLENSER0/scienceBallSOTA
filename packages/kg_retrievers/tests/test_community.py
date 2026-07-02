"""GraphRAG community detection (§11)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_retrievers.community import detect_communities
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph


def test_detect_communities_on_seed() -> None:
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(store)
    res = detect_communities(store)
    assert res.communities >= 1
    assert res.nodes_assigned >= 4
    assert all(s["summary"] for s in res.summaries)
    # community_id is written back onto entity nodes
    rows = store.rows("MATCH (n:Node) WHERE n.community_id IS NOT NULL RETURN count(n)")
    assert rows[0][0] >= 4
    store.close()

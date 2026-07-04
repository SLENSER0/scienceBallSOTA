"""api_gateway.deps.get_store: auto-seeds iff the graph is empty.

The startup emptiness check was changed from ``store.counts()['nodes'] == 0``
(two full scans, incl. a discarded relationship scan) to a cheap ``LIMIT 1`` node
probe via ``store.rows(...)``. These tests pin the behaviour-preserving decision:
seed when (and only when) the graph has no nodes.
"""

from __future__ import annotations

from pathlib import Path

from kg_common.config import get_settings
from kg_retrievers.graph_store import KuzuGraphStore


def test_get_store_seeds_empty_graph(tmp_path: Path) -> None:
    import api_gateway.deps as deps

    get_settings().kuzu_db_path = str(tmp_path / "g")
    deps.get_store.cache_clear()
    store = deps.get_store()
    # empty store -> the LIMIT-1 probe returned no rows -> seed ran
    assert not store.is_empty()
    assert store.counts()["nodes"] > 0
    deps.get_store.cache_clear()


def test_get_store_does_not_reseed_populated_graph(tmp_path: Path) -> None:
    import api_gateway.deps as deps

    db = str(tmp_path / "g")
    # pre-populate the graph, then close so deps can reopen the same path
    s = KuzuGraphStore(db)
    s.upsert_node("pre:1", "Material", name="preexisting")
    n0 = s.counts()["nodes"]
    s.close()

    get_settings().kuzu_db_path = db
    deps.get_store.cache_clear()
    store = deps.get_store()
    # probe found a node -> no seed -> the graph is untouched
    assert store.counts()["nodes"] == n0
    assert store.get_node("pre:1") is not None
    deps.get_store.cache_clear()

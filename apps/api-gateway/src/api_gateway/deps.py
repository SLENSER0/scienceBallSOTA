"""Shared singletons for the API gateway (embedded profile).

Opens the Kuzu graph store once per process and auto-seeds the demo graph if the
store is empty, so a fresh checkout answers queries immediately.
"""

from __future__ import annotations

import functools

from kg_common import get_logger, get_settings
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("api.deps")


@functools.lru_cache(maxsize=1)
def get_store() -> KuzuGraphStore:
    s = get_settings()
    s.ensure_runtime_dirs()
    store = KuzuGraphStore(s.kuzu_db_path)
    counts = store.counts()
    if counts["nodes"] == 0:
        _log.info("api.seeding_empty_graph")
        from kg_retrievers.seed import build_seed_graph

        build_seed_graph(store)
    return store

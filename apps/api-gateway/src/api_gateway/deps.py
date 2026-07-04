"""Shared singletons for the API gateway.

Opens the graph store for the active runtime profile (Kuzu embedded, or Neo4j in
the server profile — see ``kg_retrievers.store_factory``) once per process and
auto-seeds the demo graph if the store is empty, so a fresh checkout answers
queries immediately.
"""

from __future__ import annotations

import functools
from typing import Any

from kg_common import get_logger, get_settings
from kg_retrievers.store_factory import make_graph_store

_log = get_logger("api.deps")


@functools.lru_cache(maxsize=1)
def get_store() -> Any:
    s = get_settings()
    s.ensure_runtime_dirs()
    store = make_graph_store(s)
    # Cheap emptiness probe instead of counts(): a LIMIT-1 node scan short-circuits
    # at the first node and skips counts()' second full relationship scan, which is
    # computed and discarded here. Same seed-iff-empty decision. Uses rows(), shared
    # by both the Kuzu and Neo4j stores. / дешёвая проверка "пусто ли" вместо counts().
    if not store.rows("MATCH (n:Node) RETURN n LIMIT 1"):
        _log.info("api.seeding_empty_graph")
        from kg_retrievers.seed import build_seed_graph

        build_seed_graph(store)
    return store

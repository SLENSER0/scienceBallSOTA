"""Graph-store selection by runtime profile (§2/ADR-0005).

``embedded`` → Kuzu (single-process, no server); ``server`` → Neo4j over bolt.
Both stores share the same public interface (see ``graph_store.py`` /
``neo4j_store.py``), so callers are agnostic to the backend.
"""

from __future__ import annotations

from typing import Any

from kg_common import get_settings


def make_graph_store(settings: Any = None) -> Any:
    """Return the graph store for the active runtime profile.

    Imports are lazy so the embedded install never needs the neo4j driver and
    the server install never needs kuzu.
    """
    s = settings or get_settings()
    if s.runtime_profile == "server":
        from kg_retrievers.neo4j_store import Neo4jGraphStore

        return Neo4jGraphStore(s.neo4j_uri, s.neo4j_user, s.neo4j_password.get_secret_value())
    from kg_retrievers.graph_store import KuzuGraphStore

    return KuzuGraphStore(s.kuzu_db_path)

"""Hybrid-retriever selection by runtime profile (§4/§12).

``embedded`` → on-disk Qdrant-local + BM25 (``HybridRetriever.open_default``);
``server`` → the live Qdrant + OpenSearch servers, wrapped in thin adapters that
expose the ``.search(query, limit) -> hits`` / ``.count()`` contract the
``HybridRetriever`` expects (hits carry ``.id`` and ``.payload``).
"""

from __future__ import annotations

from typing import Any

from kg_common import get_logger, get_settings
from kg_retrievers.hybrid import HybridRetriever

_log = get_logger("retrieval.factory")


class _ServerHit:
    """Adapts a server-store result dict to the ``.id`` / ``.payload`` hit shape."""

    __slots__ = ("id", "payload")

    def __init__(self, d: dict[str, Any]) -> None:
        self.id = str(d.get("id"))
        self.payload = {k: v for k, v in d.items() if k != "id"}


class _StoreAdapter:
    """Wrap a server store (search(query, top_k)->list[dict], count()) as a channel."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def search(self, query: str, limit: int = 8) -> list[_ServerHit]:
        return [_ServerHit(d) for d in self._store.search(query, top_k=limit)]

    def count(self) -> int:
        try:
            return int(self._store.count())
        except Exception:
            return 0


def make_hybrid_retriever() -> HybridRetriever:
    """Return the hybrid retriever for the active runtime profile."""
    s = get_settings()
    if s.runtime_profile != "server":
        return HybridRetriever.open_default()

    vec: Any = None
    kw: Any = None
    try:
        from kg_retrievers.qdrant_server_store import QdrantServerStore

        vec = _StoreAdapter(QdrantServerStore())
    except Exception as exc:
        _log.warning("retrieval.qdrant_server_unavailable", error=str(exc)[:120])
    try:
        from kg_retrievers.opensearch_store import OpenSearchKeywordStore

        kw = _StoreAdapter(OpenSearchKeywordStore())
    except Exception as exc:
        _log.warning("retrieval.opensearch_unavailable", error=str(exc)[:120])
    return HybridRetriever(vector=vec, keyword=kw)

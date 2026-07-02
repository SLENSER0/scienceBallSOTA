"""Build vector + keyword indexes from the graph's Chunk nodes (§4)."""

from __future__ import annotations

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.keyword_store import KeywordStore
from kg_retrievers.vector_store import VectorStore

_log = get_logger("indexer")


def index_graph(
    store: KuzuGraphStore, *, limit: int | None = None, vector: bool = True
) -> dict[str, int]:
    """Index all Chunk nodes (+ Evidence text) into vector + keyword stores."""
    cy = (
        "MATCH (c:Node) WHERE c.label='Chunk' AND c.text IS NOT NULL "
        "RETURN c.id, c.text, c.doc_id, c.page"
    )
    if limit:
        cy += f" LIMIT {int(limit)}"
    rows = store.rows(cy)
    items = [
        {"id": cid, "text": text, "payload": {"doc_id": doc_id, "page": page, "kind": "chunk"}}
        for cid, text, doc_id, page in rows
    ]
    out = {"chunks": len(items), "vector": 0, "keyword": 0}
    if not items:
        return out

    kw = KeywordStore()
    out["keyword"] = kw.index(items)
    kw.save()

    if vector:
        try:
            vs = VectorStore()
            out["vector"] = vs.index(items)
        except Exception as exc:
            _log.warning("index.vector_failed", error=str(exc)[:120])
    _log.info("index.done", **out)
    return out

"""Rebuild ONLY the OpenSearch keyword index for :Chunk nodes (§4.6).

Recovery tool for when the OpenSearch ``kg_chunks`` index is lost (container restart
with a non-persistent volume) while Qdrant is intact. Keyword indexing is text-only
(no embeddings), so this reads Chunk text straight from Neo4j and bulk-indexes it —
fast, and it does NOT touch Qdrant. Idempotent.

Usage:  RUNTIME_PROFILE=server uv run python scripts/reindex_opensearch.py
"""

from __future__ import annotations

from kg_common import get_settings
from kg_retrievers.neo4j_store import Neo4jGraphStore
from kg_retrievers.opensearch_store import OpenSearchKeywordStore

BATCH = 500


def main() -> int:
    s = get_settings()
    neo = Neo4jGraphStore(s.neo4j_uri, s.neo4j_user, s.neo4j_password.get_secret_value())
    osk = OpenSearchKeywordStore()
    osk.ensure_index()

    total = 0
    buf: list[dict] = []
    rows = neo.rows("MATCH (n:Node {label:'Chunk'}) RETURN n.id, n.text, n.doc_id, n.page")
    print(f"chunks to index: {len(rows)}", flush=True)
    for cid, text, doc_id, page in rows:
        if not (text and str(text).strip()):
            continue
        buf.append({"id": cid, "text": text, "doc_id": doc_id, "page": page})
        if len(buf) >= BATCH:
            osk.index_chunks(buf)
            total += len(buf)
            buf = []
            print(f"  indexed {total}", flush=True)
    if buf:
        osk.index_chunks(buf)
        total += len(buf)

    print(f"done: indexed {total} chunks | opensearch count={osk.count()}")
    neo.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

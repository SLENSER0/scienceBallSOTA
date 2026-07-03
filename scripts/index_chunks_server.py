#!/usr/bin/env python3
"""Index the graph's :Chunk nodes into the server-profile Qdrant + OpenSearch (§4.5/§4.6).

Reads every Chunk (id/text/doc_id/page) from Neo4j, embeds + upserts into the live
Qdrant collection and bulk-indexes into the live OpenSearch index. Idempotent
(deterministic point ids / doc ids).

Usage:  uv run python scripts/index_chunks_server.py
"""

from __future__ import annotations

import sys

from kg_common import get_settings
from kg_retrievers.neo4j_store import Neo4jGraphStore
from kg_retrievers.opensearch_store import OpenSearchKeywordStore
from kg_retrievers.qdrant_server_store import QdrantServerStore

BATCH = 500


def main() -> int:
    s = get_settings()
    neo = Neo4jGraphStore(s.neo4j_uri, s.neo4j_user, s.neo4j_password.get_secret_value())
    qs = QdrantServerStore()
    qs.ensure_collection()
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
            qs.upsert_chunks(buf)
            osk.index_chunks(buf)
            total += len(buf)
            buf = []
            print(f"  indexed {total}", flush=True)
    if buf:
        qs.upsert_chunks(buf)
        osk.index_chunks(buf)
        total += len(buf)

    qc, oc = qs.count(), osk.count()
    print(f"indexed {total} chunks | qdrant={qc} opensearch={oc}")
    neo.close()
    return 0 if (qc > 0 and oc > 0) else 1


if __name__ == "__main__":
    sys.exit(main())

"""Rebuild the OpenSearch kg_chunks keyword index WITH the updated analyzer.

The scientific_text analyzer gained a Russian snowball stemmer (keyword_schema.py),
which is applied at INDEX time — so the existing index must be dropped and rebuilt for
it to take effect. Drops kg_chunks, recreates it via the current build_index_mapping()
(now including sci_russian_stem), and bulk-reindexes every Chunk's text from Neo4j.
Brief keyword-channel downtime (~1-2 min); the vector channel keeps serving.

Usage:  RUNTIME_PROFILE=server uv run python scripts/reindex_opensearch_stemmer.py
"""
from __future__ import annotations

import sys
import time

from kg_common import get_settings
from kg_retrievers.neo4j_store import Neo4jGraphStore
from kg_retrievers.opensearch_store import OpenSearchKeywordStore

BATCH = 1000


def main() -> int:
    s = get_settings()
    neo = Neo4jGraphStore(s.neo4j_uri, s.neo4j_user, s.neo4j_password.get_secret_value())
    osk = OpenSearchKeywordStore()
    osk.drop_index()  # remove the stemmer-less index
    osk.ensure_index()  # recreate with the current mapping (sci_russian_stem)
    rows = neo.rows("MATCH (n:Node {label:'Chunk'}) RETURN n.id, n.text, n.doc_id, n.page")
    print(f"chunks to index: {len(rows)}", flush=True)
    buf: list[dict] = []
    done = 0
    t0 = time.time()
    for cid, text, doc_id, page in rows:
        if not text or not str(text).strip():
            continue
        buf.append({"id": str(cid), "text": str(text), "doc_id": doc_id, "page": page})
        if len(buf) >= BATCH:
            osk.index_chunks(buf)
            done += len(buf)
            buf = []
    if buf:
        osk.index_chunks(buf)
        done += len(buf)
    cnt = osk.count()
    print(f"DONE: reindexed {done} chunks in {time.time() - t0:.0f}s | opensearch count={cnt}", flush=True)
    neo.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

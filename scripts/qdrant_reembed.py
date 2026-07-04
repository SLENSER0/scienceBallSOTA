"""Re-embed ALL :Chunk nodes into Qdrant with the CURRENT embedding model (§4.5 fix).

The live Qdrant collection held only ~18k of 52k chunks, and those were embedded with
an older fastembed pooling (CLS) than the current query-time pooling (mean) — so vector
search returned near-noise (cosine ~0.017, off-topic hits). This reads every Chunk from
Neo4j and re-embeds/upserts with the current model, making index-time and query-time
vectors consistent. Qdrant-only (does NOT touch the freshly rebuilt OpenSearch index).
Idempotent (deterministic uuid5 point ids overwrite in place).

Usage:  RUNTIME_PROFILE=server uv run python scripts/qdrant_reembed.py
"""
from __future__ import annotations

import sys
import time

from kg_common import get_logger, get_settings
from kg_retrievers.neo4j_store import Neo4jGraphStore
from kg_retrievers.qdrant_server_store import QdrantServerStore

_log = get_logger("qdrant_reembed")


def main() -> int:
    s = get_settings()
    neo = Neo4jGraphStore(s.neo4j_uri, s.neo4j_user, s.neo4j_password.get_secret_value())
    qs = QdrantServerStore()
    rows = neo.rows("MATCH (n:Node {label:'Chunk'}) RETURN n.id, n.text, n.doc_id, n.page")
    print(f"chunks in graph: {len(rows)}", flush=True)
    buf: list[dict] = []
    done = 0
    skipped = 0
    t0 = time.time()
    for cid, text, doc_id, page in rows:
        if not text or not str(text).strip():
            skipped += 1
            continue
        buf.append({"id": str(cid), "text": str(text), "doc_id": doc_id, "page": page})
        if len(buf) >= 256:
            qs.upsert_chunks(buf)
            done += len(buf)
            buf = []
            if done % 2560 == 0:
                rate = done / max(1e-6, time.time() - t0)
                print(f"[{done}/{len(rows)}] {rate:.0f} chunks/s", flush=True)
    if buf:
        qs.upsert_chunks(buf)
        done += len(buf)
    dt = time.time() - t0
    print(f"DONE: re-embedded {done} chunks (skipped {skipped} empty) into Qdrant in {dt:.0f}s", flush=True)
    neo.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

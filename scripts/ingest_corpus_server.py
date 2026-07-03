"""Batch-ingest the remaining corpus into the server-profile Neo4j graph (LLM extraction).

Only ~162 of ~1283 corpus documents were in the graph, which starved every graph-based
feature (advisor candidate pool, gap scan, coverage, briefing) — the adversarial workflows
kept hitting «недостаточно данных». This grinds through the rest with rule+LLM extraction,
writing straight into the live Neo4j (concurrent with the API — Neo4j is multi-writer,
unlike embedded Kuzu). Resumable via var/ingest_server_done.txt; the pipeline also dedups
by content hash, so a re-run never duplicates.

After it finishes (or periodically), run scripts/index_chunks_server.py to embed + index
the new Chunk nodes into Qdrant + OpenSearch for semantic/keyword retrieval.

Usage:  RUNTIME_PROFILE=server uv run python scripts/ingest_corpus_server.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from kg_common import get_logger, get_settings
from kg_retrievers.neo4j_store import Neo4jGraphStore

_log = get_logger("ingest_corpus")
_RESUME = Path("var/ingest_server_done.txt")
_MAX_MB = 80.0  # skip pathological monster files


def main() -> int:
    from ingestion_service.cli import discover
    from ingestion_service.parsers import parse_document
    from ingestion_service.pipeline import IngestionPipeline

    s = get_settings()
    store = Neo4jGraphStore(s.neo4j_uri, s.neo4j_user, s.neo4j_password.get_secret_value())

    files = discover(s.data_dir, max_mb=_MAX_MB)
    _RESUME.parent.mkdir(parents=True, exist_ok=True)
    done = set(_RESUME.read_text(encoding="utf-8").splitlines()) if _RESUME.exists() else set()
    todo = [f for f in files if str(f) not in done]
    print(f"corpus: {len(files)} files | already processed: {len(done)} | to ingest: {len(todo)}", flush=True)

    pipe = IngestionPipeline(store, use_llm=True, llm_max_chunks=3)
    fh = _RESUME.open("a", encoding="utf-8")
    t0 = time.time()
    ok = 0
    for n, f in enumerate(todo, start=1):
        try:
            parsed = parse_document(f)
            if parsed is not None:
                res = pipe.ingest(parsed)
                if res.get("status") == "ok":
                    ok += 1
        except Exception as exc:  # never let one bad doc kill the batch
            _log.warning("ingest.doc_failed", path=str(f)[:120], error=str(exc)[:140])
        fh.write(str(f) + "\n")
        fh.flush()
        if n % 10 == 0 or n <= 3:
            dt = time.time() - t0
            print(
                f"[{n}/{len(todo)}] ok={ok} nodes={store.counts()['nodes']} "
                f"({dt:.0f}s, {n / dt * 60:.1f} docs/min)",
                flush=True,
            )

    print(f"DONE: ingested {ok} new docs | graph now {store.counts()['nodes']} nodes", flush=True)
    fh.close()
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

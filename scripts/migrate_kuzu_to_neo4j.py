#!/usr/bin/env python3
"""Migrate the embedded Kuzu graph into the server-profile Neo4j (§2/§3.1).

Reads every :Node and :Rel from ``var/kuzu`` and bulk-loads them into Neo4j over
bolt using ``Neo4jGraphStore.bulk_upsert_*`` (UNWIND-MERGE, idempotent).

The embedded API gateway holds ``var/kuzu`` open read-write, so STOP it first
(``fuser -k 8000/tcp``) before running this — Kuzu is single-writer.

Usage:  uv run python scripts/migrate_kuzu_to_neo4j.py
"""

from __future__ import annotations

import contextlib
import json
import sys

from kg_common import get_settings
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.neo4j_store import Neo4jGraphStore

BATCH = 2000
_EDGE_COLS = (
    "a.id, b.id, r.type, r.confidence, r.evidence_ids, r.created_at, "
    "r.extractor_run_id, r.schema_version, r.inferred, r.contradicted, r.props"
)


def _edge_props(row: list) -> tuple[str, str, str, dict]:
    src, dst, rtype, conf, eids, created, run_id, ver, inf, contra, props_json = row
    props: dict = {}
    if conf is not None:
        props["confidence"] = conf
    if eids:
        props["evidence_ids"] = eids  # json string; Neo4j store handles both forms
    if created:
        props["created_at"] = created
    if run_id:
        props["extractor_run_id"] = run_id
    if ver:
        props["schema_version"] = ver
    if inf is not None:
        props["inferred"] = inf
    if contra is not None:
        props["contradicted"] = contra
    if props_json:
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            props.update(json.loads(props_json))
    return src, dst, (rtype or "REL"), props


def main() -> int:
    s = get_settings()
    try:
        kuzu = KuzuGraphStore(s.kuzu_db_path, read_only=True)
    except Exception:  # WAL not replayable read-only → open read-write
        kuzu = KuzuGraphStore(s.kuzu_db_path)
    neo = Neo4jGraphStore(s.neo4j_uri, s.neo4j_user, s.neo4j_password.get_secret_value())

    src_counts = kuzu.counts()
    print(f"source (kuzu): {src_counts['nodes']} nodes / {src_counts['rels']} rels")

    # -- nodes --------------------------------------------------------------
    total_n = 0
    buf: list[tuple] = []
    for r in kuzu.rows("MATCH (n:Node) RETURN n"):
        nd = kuzu._node_dict(r[0])
        nid = nd.get("id")
        if not nid:
            continue
        label = nd.get("label", "Entity")
        props = {k: v for k, v in nd.items() if k not in ("id", "label")}
        buf.append((nid, label, props))
        if len(buf) >= BATCH:
            neo.bulk_upsert_nodes(buf)
            total_n += len(buf)
            buf = []
            print(f"  nodes: {total_n}", flush=True)
    if buf:
        neo.bulk_upsert_nodes(buf)
        total_n += len(buf)
    print(f"nodes migrated: {total_n}")

    # -- edges --------------------------------------------------------------
    total_e = 0
    buf = []
    for row in kuzu.rows(f"MATCH (a:Node)-[r:Rel]->(b:Node) RETURN {_EDGE_COLS}"):
        buf.append(_edge_props(row))
        if len(buf) >= BATCH:
            neo.bulk_upsert_edges(buf)
            total_e += len(buf)
            buf = []
            print(f"  edges: {total_e}", flush=True)
    if buf:
        neo.bulk_upsert_edges(buf)
        total_e += len(buf)
    print(f"edges migrated: {total_e}")

    dst_counts = neo.counts()
    print(f"dest (neo4j): {dst_counts['nodes']} nodes / {dst_counts['rels']} rels")
    kuzu.close()
    neo.close()
    ok = dst_counts["nodes"] >= src_counts["nodes"] and dst_counts["rels"] >= src_counts["rels"]
    print("MIGRATION OK" if ok else "MIGRATION MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

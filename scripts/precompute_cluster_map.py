"""Precompute the corpus topic map → var/cluster_map.json (§17.x).

Scrolls all :Chunk vectors from the Qdrant ``kg_chunks`` collection, runs the numpy
K-Means + PCA-3D topic-map build, and writes the payload durably so the
``GET /api/v1/cluster-map`` endpoint serves it instantly (no per-request build).
Re-run after a re-ingest / re-embed to refresh the map.

Usage:  RUNTIME_PROFILE=server uv run python scripts/precompute_cluster_map.py [K]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from kg_common import get_logger, get_settings
from kg_retrievers.corpus_topic_map import fetch_and_build

_log = get_logger("precompute_cluster_map")


def main() -> int:
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    data = fetch_and_build(k=k)
    if not data.get("total"):
        print("no vectors found — is the Qdrant kg_chunks collection populated?", flush=True)
        return 1
    out = Path(get_settings().runtime_dir) / "cluster_map.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out)
    print(
        f"DONE: {data['total']} chunks → {data['k']} clusters, {data['shown']} shown, "
        f"PCA-3D var {data['var3d']}% → {out}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

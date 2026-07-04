"""Полный Dagster asset-граф + сквозная материализация seed-документа (§9.2).

§9.2 requires the *whole* ingestion/indexing pipeline to be visible as a Dagster
software-defined asset graph (≥12 assets) and one seed document to be materializable
end-to-end from ``source_registration`` to ``retrieval_eval``. Dagit (the Dagster web
UI on port 3001) is an optional container that is usually **down** in the live
server-profile, so §9.2 explicitly asks for the asset graph to be *projected into
UI/JSON when Dagit is unavailable* — that is exactly what this router does.

The canonical asset declarations, dependency edges, topological order, layer buckets
and ``define_asset_job`` subsets are reused verbatim from
:mod:`kg_common.metadata.dagster_asset_graph` (pure, Dagster-free). This router adds
the one thing that must talk to a live backend: **materialization evidence**. Every
asset names the graph-store node labels its output would create; the router counts
those nodes in the live server-profile graph (:8000 Neo4j / embedded Kuzu) — both
corpus-wide and scoped to a single seed ``doc_id`` — so the projected asset graph is
overlaid with the graph's own truth, not a mock. Assets whose real backing store is
external (Qdrant / OpenSearch / S3 / the eval harness) and therefore not queryable
from here are reported honestly as ``projected`` rather than ``materialized``.

Endpoints (prefix ``/api/v1/dagster-assets``):

* ``GET  /graph``       — the full §9.2 asset graph (assets/edges/topo/layers/jobs)
  + Dagit availability + a corpus-level materialized count per asset.
* ``GET  /jobs``        — the ``define_asset_job`` subsets, each in topo order.
* ``POST /materialize`` — end-to-end materialization projection of one seed document:
  a per-asset ``MaterializeResult`` (status + count + metadata) walked in topo order
  from ``source_registration`` to ``retrieval_eval``, plus a run summary.
"""

from __future__ import annotations

import contextlib
import re
import socket
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api_gateway.deps import get_store
from kg_common import get_settings
from kg_common.metadata.dagster_asset_graph import (
    ASSET_INDEX,
    ASSET_JOBS,
    ASSETS,
    graph_projection,
    job_asset_keys,
)

router = APIRouter(prefix="/api/v1/dagster-assets", tags=["dagster-assets"])

# Extracts the bare document hash from ids of either shape: ``doc:8b8c43b421f9398c``
# (Document/Paper/Source nodes) and ``chunk:doc-8b8c43b421f9398c-96`` /
# ``meas:doc-990099363f5a3859-chunk-...`` (downstream nodes). Scoping per-document by
# this bare hash therefore matches the source node *and* all its derived nodes,
# without needing a Document→Chunk edge.
_DOC_HASH_RE = re.compile(r"doc[:-]([0-9a-fA-F]{6,})")


# --- live graph evidence ----------------------------------------------------
def _corpus_dist(store: Any) -> dict[str, int]:
    """Corpus-wide ``label -> count`` — распределение узлов по меткам (§9.2)."""
    try:
        return {str(k): int(v) for k, v in store.counts_by_label().items()}
    except Exception:  # pragma: no cover - defensive: store may be mid-seed
        return {}


def _doc_dist(store: Any, doc_hash: str) -> dict[str, int]:
    """``label -> count`` for nodes belonging to one document — по одному doc (§9.2).

    Scopes by the bare document hash carried in node ids — matches the source
    ``doc:<hash>`` node and every derived ``…doc-<hash>…`` node (chunks, measurements,
    evidence). Portable across Neo4j and embedded Kuzu (both support ``CONTAINS``).
    """
    dist: dict[str, int] = {}
    try:
        rows = store.rows(
            "MATCH (n:Node) WHERE n.id CONTAINS $frag "
            "RETURN n.label, count(n) ORDER BY count(n) DESC",
            {"frag": doc_hash},
        )
    except Exception:  # pragma: no cover - defensive
        return dist
    for label, cnt in rows:
        if label is not None:
            dist[str(label)] = int(cnt)
    return dist


def _pick_seed_hash(store: Any) -> str | None:
    """Choose a real seed document hash — выбор seed-документа (§9.2).

    Picks the document hash that owns the most ``Chunk`` nodes, guaranteeing the seed
    has genuine downstream output to materialize end-to-end.
    """
    try:
        rows = store.rows(
            "MATCH (n:Node) WHERE n.label='Chunk' RETURN n.id LIMIT 4000"
        )
    except Exception:  # pragma: no cover - defensive
        return None
    counts: dict[str, int] = {}
    for (nid,) in rows:
        m = _DOC_HASH_RE.search(str(nid or ""))
        if m:
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    if not counts:
        return None
    return max(sorted(counts), key=lambda k: counts[k])


def _community_count(store: Any, doc_hash: str | None = None) -> int:
    """Distinct community count — число сообществ (§9.2, community_summarization).

    Tries the two property spellings seen across profiles (``community_id`` /
    ``communityId``); returns ``0`` if neither exists (community pass not run yet).
    """
    scope = "n.id CONTAINS $frag AND " if doc_hash else ""
    params = {"frag": doc_hash} if doc_hash else None
    for prop in ("community_id", "communityId"):
        with contextlib.suppress(Exception):
            rows = store.rows(
                f"MATCH (n:Node) WHERE {scope}n.{prop} IS NOT NULL "
                f"RETURN count(DISTINCT n.{prop})",
                params,
            )
            if rows and rows[0] and rows[0][0] is not None:
                return int(rows[0][0])
    return 0


def _asset_count(
    asset: Any,
    dist: dict[str, int],
    totals: dict[str, int],
    community: int,
) -> int:
    """Materialization count for one asset from a label distribution — счётчик (§9.2)."""
    if asset.aggregate == "graph_totals":
        # graph_upsert: everything the (scoped) distribution holds.
        return sum(dist.values())
    if asset.aggregate == "communities":
        return community
    return sum(dist.get(lbl, 0) for lbl in asset.evidence_labels)


def _asset_status(asset: Any, count: int) -> str:
    """Materialization status — статус материализации (§9.2).

    ``projected`` for assets whose real store (Qdrant/OpenSearch/S3/eval) is external
    and not queried here; otherwise ``materialized`` when the graph carries evidence,
    ``empty`` when it does not.
    """
    if asset.serving is not None:
        return "projected"
    return "materialized" if count > 0 else "empty"


def _dagit_available() -> dict[str, Any]:
    """Probe the optional Dagit webserver — доступность Dagit (§9.2)."""
    url = get_settings().dagster_url
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 3001)
    reachable = False
    with contextlib.suppress(OSError), socket.create_connection((host, port), timeout=0.4):
        reachable = True
    return {
        "available": reachable,
        "url": url,
        "mode": "dagit" if reachable else "projection",
    }


# --- endpoints --------------------------------------------------------------
@router.get("/graph")
def graph() -> dict[str, Any]:
    """Full §9.2 asset graph + Dagit availability + corpus materialization (§9.2).

    The pure asset graph (assets/edges/topo/layers/jobs) is overlaid with a
    corpus-wide materialized count and status per asset read from the live graph
    store, so the UI renders a real, populated Dagit fallback even when Dagit is down.
    """
    projection = graph_projection()
    store = get_store()
    corpus = _corpus_dist(store)
    totals = store.counts() if hasattr(store, "counts") else {"nodes": 0, "rels": 0}
    community = _community_count(store)

    overlay: dict[str, dict[str, Any]] = {}
    for asset in ASSETS:
        count = _asset_count(asset, corpus, totals, community)
        if asset.aggregate == "graph_totals":
            count = int(totals.get("nodes", 0))
        overlay[asset.key] = {
            "corpus_count": count,
            "status": _asset_status(asset, count),
        }
    for entry in projection["assets"]:  # type: ignore[index]
        key = entry["key"]  # type: ignore[index]
        entry.update(overlay[key])  # type: ignore[index]

    projection["dagit"] = _dagit_available()
    projection["corpus_totals"] = {
        "nodes": int(totals.get("nodes", 0)),
        "rels": int(totals.get("rels", 0)),
        "communities": community,
    }
    return projection


@router.get("/jobs")
def jobs() -> dict[str, Any]:
    """The §9.2 ``define_asset_job`` subsets, each in topological order (§9.2)."""
    return {
        "jobs": [
            {
                "name": name,
                "selection": list(keys),
                "assets": job_asset_keys(name),
                "run_closure": job_asset_keys(name, closure=True),
            }
            for name, keys in ASSET_JOBS.items()
        ]
    }


class MaterializeRequest(BaseModel):
    """Body for :func:`materialize` — параметры материализации (§9.2)."""

    doc_id: str | None = None
    job: str = "full_ingestion_job"


@router.post("/materialize")
def materialize(req: MaterializeRequest) -> dict[str, Any]:
    """End-to-end materialization of a seed document — сквозная материализация (§9.2).

    Walks the selected job's assets in topological order (default: the full
    ``source_registration → retrieval_eval`` pipeline) and, for each, returns a
    Dagster-style ``MaterializeResult``: the status, the number of graph elements it
    produced (corpus-wide for aggregating assets, scoped to the seed ``doc_id`` for
    per-document assets) and metadata. When Dagit is unavailable this *is* the §9.2
    projection of the run.
    """
    if req.job not in ASSET_JOBS:
        raise HTTPException(status_code=404, detail=f"unknown asset job: {req.job}")

    store = get_store()

    # -- resolve the seed document ------------------------------------------
    if req.doc_id:
        hash_match = _DOC_HASH_RE.search(req.doc_id)
        # accept ``doc:<hash>`` / ``doc-<hash>`` / a bare hash / any id embedding one
        doc_hash: str | None = (
            hash_match.group(1) if hash_match else (req.doc_id.split(":")[-1].strip() or None)
        )
        seed_source = "param"
    else:
        doc_hash = _pick_seed_hash(store)
        seed_source = "auto"

    if not doc_hash:
        raise HTTPException(
            status_code=404,
            detail="no seed document available in the live graph to materialize",
        )

    doc_dist = _doc_dist(store, doc_hash)
    corpus = _corpus_dist(store)
    totals = store.counts() if hasattr(store, "counts") else {"nodes": 0, "rels": 0}
    doc_community = _community_count(store, doc_hash)
    corpus_community = _community_count(store)
    doc_node_total = sum(doc_dist.values())

    order = job_asset_keys(req.job, closure=True) or [a.key for a in ASSETS]

    stages: list[dict[str, Any]] = []
    materialized = projected = empty = 0
    for pos, key in enumerate(order):
        asset = ASSET_INDEX[key]
        if asset.kind == "corpus":
            scope = "corpus"
            count = _asset_count(asset, corpus, totals, corpus_community)
            if asset.aggregate == "graph_totals":
                count = int(totals.get("nodes", 0))
        else:
            scope = "document"
            count = _asset_count(asset, doc_dist, totals, doc_community)
            if asset.aggregate == "graph_totals":
                count = doc_node_total
        status = _asset_status(asset, count)
        if status == "materialized":
            materialized += 1
        elif status == "projected":
            projected += 1
        else:
            empty += 1
        stages.append(
            {
                "order": pos,
                "key": key,
                "group": asset.group_name,
                "step": asset.step,
                "title": asset.title,
                "description": asset.description,
                "kind": asset.kind,
                "deps": list(asset.deps),
                "scope": scope,
                "status": status,
                "count": count,
                "serving": asset.serving,
                "metadata": {
                    "num_processed": count,
                    "evidence_labels": list(asset.evidence_labels),
                    "serving_store": asset.serving,
                    "aggregate": asset.aggregate,
                },
            }
        )

    return {
        "seed": {
            "doc_id": req.doc_id or f"doc:{doc_hash}",
            "fragment": doc_hash,
            "source": seed_source,
            "resolved": doc_node_total > 0,
            "node_total": doc_node_total,
            "by_label": doc_dist,
        },
        "job": req.job,
        "dagit": _dagit_available(),
        "stages": stages,
        "summary": {
            "total": len(stages),
            "materialized": materialized,
            "projected": projected,
            "empty": empty,
            "doc_nodes_total": doc_node_total,
            "corpus_nodes": int(totals.get("nodes", 0)),
            "corpus_rels": int(totals.get("rels", 0)),
        },
        "criterion": (
            "asset graph топологически совпадает с §9.1 (≥12 ассетов); "
            "материализация seed-документа проходит от source_registration до "
            "retrieval_eval"
        ),
    }

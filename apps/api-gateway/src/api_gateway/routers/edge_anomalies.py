"""Structural edge-anomaly inspector — Mode D graph hygiene surface (§13.11/§8.13).

The detector in :mod:`kg_retrievers.edge_anomalies` already *computes* the two
structural data-quality smells that the store's ``MERGE`` dedup cannot catch;
nothing yet **surfaces** them to a human. This router is that surface: it runs the
already-built :func:`kg_retrievers.edge_anomalies.detect_edge_anomalies` over the
live graph, enriches each anomalous node id with its display name/label, and hands
the Edge Anomaly Inspector a ranked, human-readable report so a curator sees
«подозрительное ребро» at a glance and broken extractions / mis-resolved
coreferences never slip through unnoticed.

Two orthogonal structural signals (§8.13), each mapped to a named anomaly kind:

* ``self_loop`` — a relationship whose source and target are the same node
  (``src == dst``); e.g. an entity that ``CONTRADICTS`` itself. Almost always a
  broken extraction or a mis-resolved coreference.
* ``parallel_edge`` — two or more edges of *differing* ``rel_type`` between the
  same ordered node pair (``a -[:MENTIONS]-> b`` **and** ``a -[:ABOUT]-> b``): the
  same directed link asserted under conflicting relation semantics.

Design (reuse, never rewrite):

* the anomaly maths lives entirely in the vendored detector — this module only
  reads the graph (via the shared store) and decorates ids with names;
* works on both runtime profiles: the detector's single base query
  ``MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id, r.type, b.id`` runs through
  ``store.rows`` on Kuzu (embedded) and Neo4j (server, :8000) alike, since both
  share the unified ``:Node`` / ``:Rel {type}`` schema;
* purely read-only — no edge is created, mutated or deleted.

One read-only endpoint (server profile, Neo4j :8000):

* ``GET /api/v1/edge-anomalies/report`` — the full structural-hygiene report:
  every self-loop and parallel edge, name-enriched, with counts and a 0–1 graph
  health score so the UI can headline «доверие к данным».
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/edge-anomalies", tags=["edge-anomalies"])

# --- named §8.13 anomaly kinds ----------------------------------------------
KIND_SELF_LOOP = "self_loop"
KIND_PARALLEL = "parallel_edge"

_KIND_LABEL_RU: dict[str, str] = {
    KIND_SELF_LOOP: "петля (ребро на самого себя)",
    KIND_PARALLEL: "параллельные рёбра (конфликт семантики связи)",
}


# --------------------------------------------------------------------------- IO
class SelfLoopItem(BaseModel):
    """A relationship whose endpoints are the same node (§8.13)."""

    kind: str = KIND_SELF_LOOP
    node_id: str
    node_name: str | None
    node_label: str | None
    rel_type: str
    label_ru: str
    reason: str


class ParallelEdgeItem(BaseModel):
    """Two+ edges of differing ``rel_type`` on one ordered node pair (§8.13)."""

    kind: str = KIND_PARALLEL
    src_id: str
    src_name: str | None
    src_label: str | None
    dst_id: str
    dst_name: str | None
    dst_label: str | None
    rel_types: list[str]
    label_ru: str
    reason: str


class EdgeAnomalyReport(BaseModel):
    """Structural graph-hygiene report (§13.11/§8.13)."""

    total_edges: int
    n_self_loops: int
    n_parallel_edges: int
    n_anomalies: int
    ok: bool
    # Fraction of edges free of a structural smell, in [0, 1] — «доверие к данным».
    health_score: float
    counts: dict[str, int]
    self_loops: list[SelfLoopItem]
    parallel_edges: list[ParallelEdgeItem]
    truncated: bool


# ------------------------------------------------------------------- graph read
def _node_names(store, node_ids: set[str]) -> dict[str, tuple[str | None, str | None]]:  # type: ignore[no-untyped-def]
    """Resolve ``id -> (name, label)`` for the anomalous node ids only.

    Best-effort: a node that cannot be read (deleted, or the store lacks
    ``get_node``) simply maps to ``(None, None)`` — the inspector still lists the
    raw id, it just cannot show a friendly name.
    """
    out: dict[str, tuple[str | None, str | None]] = {}
    getter = getattr(store, "get_node", None)
    for nid in node_ids:
        name: str | None = None
        label: str | None = None
        if callable(getter):
            try:
                node = getter(nid)
            except Exception:  # never let one bad node break the report
                node = None
            if isinstance(node, dict):
                raw_name = node.get("name")
                raw_label = node.get("label")
                name = str(raw_name) if raw_name not in (None, "") else None
                label = str(raw_label) if raw_label not in (None, "") else None
        out[str(nid)] = (name, label)
    return out


def _display(node_id: str, name: str | None, label: str | None) -> str:
    """Short human token for a node in a reason string (имя · тип, либо id)."""
    if name and label:
        return f"«{name}» · {label}"
    if name:
        return f"«{name}»"
    return node_id


# ------------------------------------------------------------------- endpoint
@router.get("/report", response_model=EdgeAnomalyReport)
def report(
    limit: int = Query(default=500, ge=1, le=5000, description="макс. элементов на секцию"),
) -> EdgeAnomalyReport:
    """Structural edge-anomaly report over the live graph (§13.11 Mode D / §8.13).

    Runs the already-built structural detector over every ``:Rel`` edge, enriches
    each flagged node with its display name/label and returns self-loops and
    parallel edges (name-resolved) with counts and a 0–1 health score. Each
    section is capped at *limit* items so a pathological graph never returns an
    unbounded payload; ``truncated`` reports whether any cap was hit.
    """
    from kg_retrievers.edge_anomalies import detect_edge_anomalies

    store = get_store()
    rep = detect_edge_anomalies(store)

    # Cap each section independently to keep the payload bounded.
    self_loops = list(rep.self_loops)
    parallel = list(rep.parallel_edges)
    truncated = len(self_loops) > limit or len(parallel) > limit
    self_loops = self_loops[:limit]
    parallel = parallel[:limit]

    # Resolve names for exactly the ids we will show — one pass, deduped.
    ids: set[str] = {s.node_id for s in self_loops}
    for p in parallel:
        ids.add(p.src_id)
        ids.add(p.dst_id)
    names = _node_names(store, ids)

    loop_items: list[SelfLoopItem] = []
    for s in self_loops:
        name, label = names.get(s.node_id, (None, None))
        loop_items.append(
            SelfLoopItem(
                node_id=s.node_id,
                node_name=name,
                node_label=label,
                rel_type=s.rel_type,
                label_ru=_KIND_LABEL_RU[KIND_SELF_LOOP],
                reason=(
                    f"узел {_display(s.node_id, name, label)} связан сам с собой "
                    f"через «{s.rel_type}» — вероятно сломанная экстракция или "
                    f"ошибочная кореференция"
                ),
            )
        )

    par_items: list[ParallelEdgeItem] = []
    for p in parallel:
        sname, slabel = names.get(p.src_id, (None, None))
        dname, dlabel = names.get(p.dst_id, (None, None))
        rel_types = list(p.rel_types)
        par_items.append(
            ParallelEdgeItem(
                src_id=p.src_id,
                src_name=sname,
                src_label=slabel,
                dst_id=p.dst_id,
                dst_name=dname,
                dst_label=dlabel,
                rel_types=rel_types,
                label_ru=_KIND_LABEL_RU[KIND_PARALLEL],
                reason=(
                    f"{_display(p.src_id, sname, slabel)} → "
                    f"{_display(p.dst_id, dname, dlabel)} утверждается "
                    f"под {len(rel_types)} разными типами связи: "
                    f"{', '.join(rel_types)} — конфликт семантики"
                ),
            )
        )

    n_self = len(rep.self_loops)
    n_par = len(rep.parallel_edges)
    n_anom = n_self + n_par
    total = rep.total_edges
    # Health = share of edges with no structural smell. Each parallel-edge group
    # collapses ≥2 edges into one anomaly, so the score is a conservative floor.
    health = 1.0 if total <= 0 else max(0.0, 1.0 - n_anom / total)

    return EdgeAnomalyReport(
        total_edges=total,
        n_self_loops=n_self,
        n_parallel_edges=n_par,
        n_anomalies=n_anom,
        ok=rep.ok,
        health_score=round(health, 6),
        counts={KIND_SELF_LOOP: n_self, KIND_PARALLEL: n_par},
        self_loops=loop_items,
        parallel_edges=par_items,
        truncated=truncated,
    )

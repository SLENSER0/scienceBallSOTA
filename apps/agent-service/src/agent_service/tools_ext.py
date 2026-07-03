"""Extended agent tools — reaching the full §7.4 named-tool set (§13.6).

``agent_service.tools`` ships a focused, dependency-light subset of the retrieval
tool layer (6 tools: ``graph_search`` / ``numeric_filter`` / ``evidence_lookup`` /
``gap_check`` / ``compare_practice`` / ``global_search``). The §7.4 design, however,
enumerates a **stable set of 16 named tools** that the LLM tool-caller and the
retrieval orchestrator (§7.5) expect. This module adds the missing named tools as
thin, side-effect-light callables that *delegate to the existing retrievers / store*
— no new retrieval logic, no stubs.

Реализовано здесь (12 of the 16 §7.4 tools):

    resolve_entities              — alias/fuzzy resolve of mentions (reuse AliasIndex)
    search_material_aliases       — material alias lookup (reuse AliasIndex)
    run_cypher_template           — parameterized read-only template exec (via store.rows)
    vector_search_qdrant          — dense (Qdrant) or offline sparse embedding search
    keyword_search_opensearch     — BM25 lexical search (reuse KeywordStore)
    hybrid_search                 — RRF fusion of vector + keyword (reuse hybrid.RRF_K)
    get_experiment_table          — TablePayload of experiments/measurements (§6.2)
    get_document_snippet          — document span fragment for inline-citation
    find_graph_paths              — shortest Material↔Property path (reuse graph_algos)
    expand_subgraph               — N-hop subgraph projection (reuse store.subgraph_from_ids)
    detect_contradictions         — conflicting measurements (reuse contradiction_detector)
    create_review_task            — curation review-task draft (§12.1)

The remaining 4 §7.4 names live in :data:`BASE_SPEC_TOOL_NAMES` — they are already
served by ``agent_service.tools`` (``get_evidence_by_ids`` ≈ ``tool_evidence_lookup``;
``scan_gaps`` ≈ ``tool_gap_check``) or wired separately by the parent
(``run_cypher_readonly`` guarded Text2Cypher executor; ``build_graph_visualization_payload``
GraphResponse builder). Together they make :data:`ALL_TOOL_NAMES` — exactly the 16
§7.4 names (``12 implemented here + 4 base = 16``).

Each tool is exported both as a plain ``(store, **args) -> dict`` callable (for direct
use / testing) and as a :class:`~agent_service.tools.Tool` descriptor in
:data:`EXTRA_TOOLS`, which the parent merges into the agent registry. Everything is
read-only w.r.t. the graph and returns JSON-serialisable ``dict``s.

Kuzu note (§3): only the typed :data:`~kg_retrievers.graph_store.NODE_COLUMNS` are
queryable columns — custom props live in the ``props`` JSON and are read back via
``store.get_node`` rather than matched/returned directly.
"""

from __future__ import annotations

import contextlib
import json
import re
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_service.tools import Tool
from kg_common import uuid5_id
from kg_retrievers.alias_index import AliasIndex
from kg_retrievers.contradiction_detector import detect_contradiction
from kg_retrievers.graph_algos import shortest_path
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.hybrid import RRF_K
from kg_retrievers.keyword_store import KeywordStore
from kg_retrievers.sparse import SparseIndex
from kg_schema.labels import ENTITY_LABELS

# Node labels treated as materials / processes for the material-alias and experiment
# tools (§8.1). Kept as frozensets for O(1) membership and determinism.
MATERIAL_KINDS: frozenset[str] = frozenset({"Material", "Alloy", "ChemicalElement", "Composition"})
PROCESS_KINDS: frozenset[str] = frozenset(
    {"ProcessingRegime", "Method", "TechnologySolution", "ProcessingStep", "Equipment"}
)
EVIDENCE_KINDS: frozenset[str] = frozenset({"Evidence", "Paper"})

# Fixed column order of the experiment TablePayload (§6.2 «Пример ответа»).
EXPERIMENT_COLUMNS: tuple[str, ...] = (
    "id",
    "material",
    "processing",
    "property",
    "value",
    "unit",
    "effect",
    "confidence",
    "evidence_ids",
)

# Reasons that warrant a top-priority review task (§12.1 auto-review triggers).
HIGH_PRIORITY_REASONS: frozenset[str] = frozenset(
    {"contradiction", "ambiguous_er", "missing_critical_field", "low_confidence"}
)

# Cypher clauses that mutate the graph — forbidden in read-only templates (§13.5).
_WRITE_CLAUSE = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|COPY|LOAD|INSTALL|ALTER|ATTACH)\b",
    re.IGNORECASE,
)

# An ephemeral (never-persisted) path for on-the-fly lexical indexes: KeywordStore only
# reads from disk if the pickle already exists (it never will here) and we never save.
_EPHEMERAL_INDEX = str(Path(tempfile.gettempdir()) / "kg_agent_tools_ext_scratch")


# ---------------------------------------------------------------------------
# Small frozen result shapes (house style: frozen dataclasses w/ as_dict)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SearchHit:
    """One ranked retrieval hit (§7.5 Node 6) — узел графа с оценкой релевантности."""

    id: str
    score: float
    backend: str
    label: str
    name: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "score": self.score,
            "backend": self.backend,
            "label": self.label,
            "name": self.name,
        }


@dataclass(frozen=True)
class ResolvedMention:
    """A mention resolved to a canonical entity id with candidates (§7.5 Node 3)."""

    mention: str
    entity_id: str | None
    confidence: float
    label: str | None
    name: str | None
    candidates: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "mention": self.mention,
            "entity_id": self.entity_id,
            "confidence": self.confidence,
            "label": self.label,
            "name": self.name,
            "candidates": list(self.candidates),
        }


@dataclass(frozen=True)
class CypherTemplate:
    """A named, parameterized **read-only** Cypher template (§7.4 / §13.5).

    ``cypher`` never contains string-concatenated user input — every value is bound
    through ``$``-parameters at execution time; a safe integer ``LIMIT`` is appended
    by :func:`run_cypher_template`. ``params`` lists the required parameter names.
    """

    name: str
    cypher: str
    params: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "cypher": self.cypher, "params": list(self.params)}


@dataclass(frozen=True)
class ReviewTaskDraft:
    """A curation review-task draft — черновик задачи ревью (§12.1).

    Deterministic (``task_id`` is a uuid5 of target + reason) so re-emitting the same
    signal does not create a duplicate. The parent enqueues it into the curation
    review queue (``kg_common.storage.review_queue``); this builder only shapes and
    validates the DTO against the store.
    """

    task_id: str
    target_type: str
    target_id: str
    reason: str
    status: str
    priority: float
    target_exists: bool
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "reason": self.reason,
            "status": self.status,
            "priority": self.priority,
            "target_exists": self.target_exists,
            "payload": self.payload,
        }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _safe_k(value: Any, default: int = 8) -> int:
    """Coerce a ``top_k`` to a sane positive int in ``[1, 100]``."""
    try:
        return max(1, min(int(value), 100))
    except (TypeError, ValueError):
        return default


def _safe_limit(value: Any, default: int = 50) -> int:
    """Coerce a row ``LIMIT`` to a safe int in ``[1, 1000]`` (never a raw string)."""
    try:
        return max(1, min(int(value), 1000))
    except (TypeError, ValueError):
        return default


def _filter_scope(filters: Mapping[str, Any] | None) -> tuple[list[str] | None, str | None]:
    """Extract an optional ``(labels, domain)`` scope from a filters dict."""
    f = filters or {}
    labels = f.get("labels")
    if not labels and f.get("label"):
        labels = [f["label"]]
    return (list(labels) if labels else None), f.get("domain")


def _node_corpus(
    store: KuzuGraphStore,
    *,
    labels: Iterable[str] | None = None,
    domain: str | None = None,
) -> list[dict[str, Any]]:
    """Build a ``[{id, text, label, name, domain}]`` corpus from queryable columns.

    ``text`` folds name + canonical_name + document text + pipe-split aliases into one
    searchable blob (§3.12). The WHERE clause is assembled from fixed fragments only;
    all values are bound as ``$``-parameters (no string injection).
    """
    where: list[str] = []
    params: dict[str, Any] = {}
    if labels:
        where.append("n.label IN $labels")
        params["labels"] = list(labels)
    if domain:
        where.append("n.domain = $domain")
        params["domain"] = domain
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    rows = store.rows(
        "MATCH (n:Node)"
        + clause
        + " RETURN n.id, n.label, n.name, n.canonical_name, n.aliases_text, n.text, n.domain",
        params,
    )
    corpus: list[dict[str, Any]] = []
    for nid, label, name, canon, aliases, text, dom in rows:
        parts = [str(p) for p in (name, canon, text) if p]
        if aliases:
            parts.extend(a for a in str(aliases).split("|") if a.strip())
        blob = " ".join(parts).strip()
        if not nid or not blob:
            continue
        corpus.append(
            {
                "id": nid,
                "text": blob,
                "label": label or "Node",
                "name": name or canon or nid,
                "domain": dom,
            }
        )
    return corpus


def _rrf_fuse(rank_lists: Iterable[list[str]]) -> list[tuple[str, float]]:
    """Reciprocal-rank fusion of several ranked id lists (§10.2), reusing ``RRF_K``."""
    scores: dict[str, float] = {}
    for ids in rank_lists:
        for rank, nid in enumerate(ids):
            scores[nid] = scores.get(nid, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def assert_read_only_cypher(cypher: str) -> None:
    """Raise ``ValueError`` if ``cypher`` contains any mutating clause (§13.5 guard).

    Defense-in-depth for :func:`run_cypher_template`: even a template that slipped a
    write clause is refused before it can reach the store.
    """
    match = _WRITE_CLAUSE.search(cypher or "")
    if match:
        raise ValueError(f"mutating clause not allowed in read template: {match.group(1).upper()}")


# ---------------------------------------------------------------------------
# Read-only Cypher templates (§7.4 / §13.5, Mode A)
# ---------------------------------------------------------------------------
CYPHER_TEMPLATES: dict[str, CypherTemplate] = {
    "nodes_by_label": CypherTemplate(
        "nodes_by_label",
        "MATCH (n:Node) WHERE n.label = $label RETURN n.id, n.label, n.name",
        ("label",),
    ),
    "node_by_id": CypherTemplate(
        "node_by_id",
        "MATCH (n:Node) WHERE n.id = $id RETURN n.id, n.label, n.name",
        ("id",),
    ),
    "entity_neighbors": CypherTemplate(
        "entity_neighbors",
        "MATCH (a:Node)-[r:Rel]-(b:Node) WHERE a.id = $id RETURN b.id, b.label, r.type",
        ("id",),
    ),
    "measurements_by_property": CypherTemplate(
        "measurements_by_property",
        "MATCH (n:Node) WHERE n.label = 'Measurement' AND n.property_name = $property "
        "RETURN n.id, n.property_name, n.value_normalized, n.normalized_unit",
        ("property",),
    ),
}


# ---------------------------------------------------------------------------
# Tool implementations — each is (store, **args) -> dict, real delegation
# ---------------------------------------------------------------------------
def resolve_entities(
    store: KuzuGraphStore,
    *,
    mentions: Any = None,
    context: Any = None,
    limit: int = 5,
    labels: Iterable[str] | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Resolve raw mentions to canonical entity ids (§7.5 Node 3, reuse AliasIndex).

    For each mention: exact alias hit first (confidence ``1.0``), else the top
    token-overlap candidate; every mention also carries its ranked ``candidates`` so
    the agent can ask for disambiguation only when it blocks the answer (§7.6).
    """
    index = AliasIndex.build_from_store(store, labels=labels or ENTITY_LABELS)
    raw = mentions if isinstance(mentions, (list, tuple)) else ([mentions] if mentions else [])
    resolved: list[dict[str, Any]] = []
    for item in raw:
        mention = str(item)
        exact = index.lookup_exact(mention)
        ranked = index.search(mention, _safe_k(limit))
        candidates: list[dict[str, Any]] = []
        for eid, score in ranked:
            entry = index.entry(eid)
            candidates.append(
                {
                    "entity_id": eid,
                    "score": round(float(score), 6),
                    "name": entry.name if entry else eid,
                    "label": entry.label if entry else None,
                }
            )
        best = exact or (ranked[0][0] if ranked else None)
        confidence = 1.0 if exact else (round(float(ranked[0][1]), 6) if ranked else 0.0)
        entry = index.entry(best) if best else None
        resolved.append(
            ResolvedMention(
                mention=mention,
                entity_id=best,
                confidence=confidence,
                label=entry.label if entry else None,
                name=entry.name if entry else None,
                candidates=tuple(candidates),
            ).as_dict()
        )
    return {"mentions": resolved, "count": len(resolved), "context": context}


def search_material_aliases(
    store: KuzuGraphStore,
    *,
    name: str = "",
    limit: int = 10,
    entity_type: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Search material entities by alias / surface form (§7.4, reuse AliasIndex).

    Ranks by token overlap and keeps only material-family labels by default
    (:data:`MATERIAL_KINDS`); pass ``entity_type`` to pin a single label.
    """
    index = AliasIndex.build_from_store(store, labels=ENTITY_LABELS)
    k = _safe_k(limit, default=10)
    matches: list[dict[str, Any]] = []
    for eid, score in index.search(str(name), k * 4):
        entry = index.entry(eid)
        label = entry.label if entry else None
        if entity_type is not None:
            if label != entity_type:
                continue
        elif label not in MATERIAL_KINDS:
            continue
        matches.append(
            {
                "entity_id": eid,
                "score": round(float(score), 6),
                "label": label,
                "name": entry.name if entry else eid,
            }
        )
        if len(matches) >= k:
            break
    return {"query": name, "matches": matches, "count": len(matches)}


def run_cypher_template(
    store: KuzuGraphStore,
    *,
    template_name: str,
    params: Mapping[str, Any] | None = None,
    limit: int = 50,
    templates: Mapping[str, CypherTemplate | str] | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Execute a named, parameterized **read-only** Cypher template (§7.4 / §13.5).

    Only allow-listed templates run — there is no raw-Cypher path. The template body
    is guarded with :func:`assert_read_only_cypher` (rejects any mutating clause) and
    executed via ``store.rows`` with a safe integer ``LIMIT`` appended; all filter
    values are bound as ``$``-parameters. ``templates`` overrides the default registry
    (used to inject a test template) but is subject to the same read-only guard.
    """
    registry = templates if templates is not None else CYPHER_TEMPLATES
    if template_name not in registry:
        raise ValueError(f"unknown cypher template: {template_name!r}")
    template = registry[template_name]
    cypher = template.cypher if isinstance(template, CypherTemplate) else str(template)
    assert_read_only_cypher(cypher)
    n = _safe_limit(limit)
    rows = store.rows(f"{cypher} LIMIT {n}", dict(params or {}))
    return {
        "template": template_name,
        "rows": [list(r) for r in rows],
        "count": len(rows),
    }


def keyword_search(
    store: KuzuGraphStore,
    *,
    query: str = "",
    top_k: int = 8,
    filters: Mapping[str, Any] | None = None,
    keyword: KeywordStore | None = None,
    **_: Any,
) -> dict[str, Any]:
    """BM25 lexical search (§7.4 ``keyword_search_opensearch``, reuse KeywordStore).

    Delegates to a pre-built :class:`KeywordStore` when supplied (server profile);
    otherwise builds a throwaway in-process BM25 index over the graph's node text —
    the embedded-profile substitute for OpenSearch (§4 / ADR-0005).
    """
    k = _safe_k(top_k)
    labels, domain = _filter_scope(filters)
    store_kw = keyword
    if store_kw is None:
        store_kw = KeywordStore(path=_EPHEMERAL_INDEX)
        store_kw.index(
            [
                {
                    "id": c["id"],
                    "text": c["text"],
                    "payload": {"label": c["label"], "name": c["name"], "domain": c["domain"]},
                }
                for c in _node_corpus(store, labels=labels, domain=domain)
            ]
        )
    hits = [
        SearchHit(
            id=h.id,
            score=round(float(h.score), 6),
            backend="bm25",
            label=str(h.payload.get("label", "Node")),
            name=str(h.payload.get("name", h.id)),
        ).as_dict()
        for h in store_kw.search(str(query), k)
    ]
    return {"query": query, "backend": "bm25", "hits": hits, "count": len(hits)}


def vector_search(
    store: KuzuGraphStore,
    *,
    query: str = "",
    top_k: int = 8,
    filters: Mapping[str, Any] | None = None,
    vector: Any = None,
    **_: Any,
) -> dict[str, Any]:
    """Vector search (§7.4 ``vector_search_qdrant``): dense Qdrant or offline sparse.

    When a dense :class:`~kg_retrievers.vector_store.VectorStore` is supplied, uses it
    (``mode='dense'``). Otherwise falls back to the dependency-free sparse embedding
    channel (:class:`~kg_retrievers.sparse.SparseIndex`, SPLADE-lite, §4.4) built over
    the graph's node text — the embedded-profile substitute (``mode='sparse'``).
    """
    k = _safe_k(top_k)
    labels, domain = _filter_scope(filters)
    if vector is not None:
        hits = [
            SearchHit(
                id=h.id,
                score=round(float(h.score), 6),
                backend="qdrant-dense",
                label=str(h.payload.get("label", "Node")),
                name=str(h.payload.get("name", h.id)),
            ).as_dict()
            for h in vector.search(str(query), k)
        ]
        return {
            "query": query,
            "mode": "dense",
            "backend": "qdrant-dense",
            "hits": hits,
            "count": len(hits),
        }
    index = SparseIndex()
    meta: dict[str, dict[str, Any]] = {}
    for c in _node_corpus(store, labels=labels, domain=domain):
        index.add(c["id"], c["text"])
        meta[c["id"]] = c
    hits = [
        SearchHit(
            id=nid,
            score=round(float(score), 6),
            backend="sparse",
            label=str(meta[nid]["label"]),
            name=str(meta[nid]["name"]),
        ).as_dict()
        for nid, score in index.search(str(query), k)
    ]
    return {"query": query, "mode": "sparse", "backend": "sparse", "hits": hits, "count": len(hits)}


def hybrid_search(
    store: KuzuGraphStore,
    *,
    query: str = "",
    top_k: int = 8,
    filters: Mapping[str, Any] | None = None,
    vector: Any = None,
    keyword: KeywordStore | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Hybrid search (§7.4): reciprocal-rank fusion of vector + keyword (§10.2).

    Runs :func:`vector_search` and :func:`keyword_search` and fuses their rankings with
    RRF (reusing ``kg_retrievers.hybrid.RRF_K``), so a document ranked well by either
    channel surfaces. Passing pre-built ``vector`` / ``keyword`` stores routes to the
    real dense/BM25 backends; otherwise the offline substitutes are used.
    """
    k = _safe_k(top_k)
    kw_hits = keyword_search(store, query=query, top_k=k * 2, filters=filters, keyword=keyword)[
        "hits"
    ]
    vec_hits = vector_search(store, query=query, top_k=k * 2, filters=filters, vector=vector)[
        "hits"
    ]
    meta: dict[str, dict[str, Any]] = {h["id"]: h for h in (*vec_hits, *kw_hits)}
    fused = _rrf_fuse([[h["id"] for h in kw_hits], [h["id"] for h in vec_hits]])
    hits = [
        SearchHit(
            id=nid,
            score=round(float(score), 6),
            backend="hybrid_rrf",
            label=str(meta.get(nid, {}).get("label", "Node")),
            name=str(meta.get(nid, {}).get("name", nid)),
        ).as_dict()
        for nid, score in fused[:k]
    ]
    return {"query": query, "backend": "hybrid_rrf", "hits": hits, "count": len(hits)}


def _experiment_context(
    store: KuzuGraphStore, measurement_id: str
) -> tuple[str | None, str | None, list[str]]:
    """Find the material, processing and evidence ids linked to a measurement."""
    rows = store.rows(
        "MATCH (m:Node)-[r:Rel]-(x:Node) WHERE m.id = $id "
        "RETURN x.id, x.label, x.name, r.type, r.evidence_ids",
        {"id": measurement_id},
    )
    material: str | None = None
    processing: str | None = None
    evidence: set[str] = set()
    for xid, xlabel, xname, _rtype, eids in rows:
        if material is None and xlabel in MATERIAL_KINDS:
            material = xname or xid
        if processing is None and xlabel in PROCESS_KINDS:
            processing = xname or xid
        if xlabel in EVIDENCE_KINDS:
            evidence.add(xid)
        if eids:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                evidence.update(json.loads(eids))
    return material, processing, sorted(evidence)


def get_experiment_table(
    store: KuzuGraphStore,
    *,
    filters: Mapping[str, Any] | None = None,
    limit: int = 50,
    **_: Any,
) -> dict[str, Any]:
    """Return a TablePayload of experiment measurements (§7.4 / §6.2 «Пример ответа»).

    Rows carry ``id, material, processing, property, value, unit, effect, confidence,
    evidence_ids`` — the material / processing / evidence are followed from the
    measurement's edges. ``effect`` reads ``effect_direction`` (a custom prop, via
    ``get_node``) falling back to the typed ``polarity`` column.
    """
    _labels, domain = _filter_scope(filters)
    prop = (filters or {}).get("property")
    where = ["m.label = 'Measurement'"]
    params: dict[str, Any] = {}
    if prop:
        where.append("m.property_name = $property")
        params["property"] = prop
    if domain:
        where.append("m.domain = $domain")
        params["domain"] = domain
    n = _safe_limit(limit)
    rows = store.rows(
        "MATCH (m:Node) WHERE "
        + " AND ".join(where)
        + " RETURN m.id, m.property_name, m.value_normalized, m.normalized_unit, "
        "m.confidence, m.polarity" + f" LIMIT {n}",
        params,
    )
    table: list[dict[str, Any]] = []
    for mid, pname, value, unit, confidence, polarity in rows:
        material, processing, evidence_ids = _experiment_context(store, mid)
        full = store.get_node(mid) or {}
        table.append(
            {
                "id": mid,
                "material": material,
                "processing": processing,
                "property": pname,
                "value": value,
                "unit": unit,
                "effect": full.get("effect_direction") or polarity,
                "confidence": confidence,
                "evidence_ids": evidence_ids,
            }
        )
    return {"columns": list(EXPERIMENT_COLUMNS), "rows": table, "count": len(table)}


def get_document_snippet(
    store: KuzuGraphStore,
    *,
    doc_id: str | None = None,
    page: int | None = None,
    span: Any = None,
    evidence_id: str | None = None,
    max_chars: int = 400,
    **_: Any,
) -> dict[str, Any]:
    """Return a document-span fragment for inline-citation (§7.4).

    Resolves either a specific ``evidence_id`` or the first Evidence node for a
    ``doc_id`` (optionally pinned to ``page``); ``span=[start, end]`` slices the stored
    text, otherwise it is truncated to ``max_chars``.
    """
    node: dict[str, Any] | None = None
    if evidence_id:
        node = store.get_node(str(evidence_id))
    elif doc_id:
        rows = store.rows(
            "MATCH (n:Node) WHERE n.label = 'Evidence' AND n.doc_id = $doc "
            "RETURN n.id, n.doc_id, n.page, n.text",
            {"doc": str(doc_id)},
        )
        for nid, ndoc, npage, ntext in rows:
            if page is not None and npage != page:
                continue
            node = {"id": nid, "doc_id": ndoc, "page": npage, "text": ntext}
            break
    if not node:
        return {
            "doc_id": doc_id,
            "page": page,
            "evidence_id": evidence_id,
            "snippet": "",
            "found": False,
        }
    text = str(node.get("text") or "")
    if isinstance(span, (list, tuple)) and len(span) == 2:
        with contextlib.suppress(TypeError, ValueError):
            text = text[int(span[0]) : int(span[1])]
    else:
        text = text[: max(1, int(max_chars))]
    return {
        "doc_id": node.get("doc_id", doc_id),
        "page": node.get("page", page),
        "evidence_id": node.get("id", evidence_id),
        "snippet": text,
        "found": True,
    }


def find_graph_paths(
    store: KuzuGraphStore,
    *,
    source_id: str = "",
    target_id: str = "",
    max_hops: int = 4,
    **_: Any,
) -> dict[str, Any]:
    """Shortest entity path between two nodes (§7.4, reuse graph_algos.shortest_path).

    Returns ``paths`` as a list of node-id paths (one shortest path, or empty when the
    pair is disconnected or exceeds ``max_hops``). ``hops`` is the edge count.
    """
    path = shortest_path(store, str(source_id), str(target_id))
    within = bool(path) and (len(path) - 1) <= int(max_hops)
    return {
        "source": source_id,
        "target": target_id,
        "paths": [path] if within else [],
        "found": within,
        "hops": (len(path) - 1) if within else None,
        "max_hops": int(max_hops),
    }


def expand_subgraph(
    store: KuzuGraphStore,
    *,
    node_ids: Any = None,
    depth: int = 1,
    types: Iterable[str] | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Expand an N-hop subgraph around seed nodes (§7.4, reuse subgraph_from_ids).

    Projects the seeds plus their ``depth``-hop neighbourhood, optionally filtering
    nodes (and dangling edges) to the given ``types`` (§5.2.3 subgraph projection).
    """
    seeds = [
        str(i)
        for i in (
            node_ids if isinstance(node_ids, (list, tuple)) else [node_ids] if node_ids else []
        )
    ]
    response = store.subgraph_from_ids(seeds, expand=max(0, int(depth)))
    type_filter = set(types) if types else None
    nodes = [n for n in response.nodes if type_filter is None or n.type in type_filter]
    keep = {n.id for n in nodes}
    edges = [e for e in response.edges if e.source in keep and e.target in keep]
    return {
        "seed_ids": seeds,
        "depth": max(0, int(depth)),
        "nodes": [
            {
                "id": n.id,
                "type": n.type,
                "label": n.label,
                "confidence": n.confidence,
                "community_id": n.community_id,
            }
            for n in nodes
        ],
        "edges": [
            {"source": e.source, "target": e.target, "type": e.type, "confidence": e.confidence}
            for e in edges
        ],
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def detect_contradictions(
    store: KuzuGraphStore,
    *,
    filters: Mapping[str, Any] | None = None,
    property: str | None = None,
    limit: int = 100,
    **_: Any,
) -> dict[str, Any]:
    """Find conflicting measurements of the same property (§7.4, reuse detector §15.4).

    Groups Measurement nodes by ``property_name`` and runs
    :func:`~kg_retrievers.contradiction_detector.detect_contradiction` over each pair;
    every contradicting pair is reported with its subtype / severity / reasons, sorted
    most-severe first.
    """
    _labels, domain = _filter_scope(filters)
    prop = property or (filters or {}).get("property")
    where = ["m.label = 'Measurement'"]
    params: dict[str, Any] = {}
    if prop:
        where.append("m.property_name = $property")
        params["property"] = prop
    if domain:
        where.append("m.domain = $domain")
        params["domain"] = domain
    n = _safe_limit(limit)
    ids = [
        r[0]
        for r in store.rows(
            "MATCH (m:Node) WHERE " + " AND ".join(where) + f" RETURN m.id LIMIT {n}", params
        )
    ]
    groups: dict[str, list[dict[str, Any]]] = {}
    for nid in ids:
        node = store.get_node(nid)
        if node:
            groups.setdefault(str(node.get("property_name") or ""), []).append(node)
    found: list[dict[str, Any]] = []
    for pname, measures in groups.items():
        for i in range(len(measures)):
            for j in range(i + 1, len(measures)):
                verdict = detect_contradiction(measures[i], measures[j])
                if verdict.is_contradiction:
                    found.append(
                        {
                            "property": pname,
                            "a_id": measures[i].get("id"),
                            "b_id": measures[j].get("id"),
                            **verdict.as_dict(),
                        }
                    )
    found.sort(key=lambda r: (-r["severity"], r.get("a_id") or "", r.get("b_id") or ""))
    return {"contradictions": found, "count": len(found)}


def create_review_task(
    store: KuzuGraphStore,
    *,
    target_type: str = "",
    target_id: str = "",
    reason: str = "",
    payload: Mapping[str, Any] | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Draft a curation review task (§7.4 / §12.1 auto-review triggers).

    Builds a deterministic :class:`ReviewTaskDraft` (uuid5 of target + reason, so
    duplicates collapse), assigns a priority from the reason and validates that the
    target exists in the store. The parent enqueues the draft into the curation review
    queue (``kg_common.storage.review_queue``).
    """
    reason_s = str(reason or "")
    task_id = uuid5_id("CurationEvent", str(target_type), str(target_id), reason_s)
    exists = bool(target_id) and store.get_node(str(target_id)) is not None
    priority = 1.0 if reason_s in HIGH_PRIORITY_REASONS else 0.5
    return ReviewTaskDraft(
        task_id=task_id,
        target_type=str(target_type or ""),
        target_id=str(target_id or ""),
        reason=reason_s,
        status="open",
        priority=priority,
        target_exists=exists,
        payload=dict(payload or {}),
    ).as_dict()


# ---------------------------------------------------------------------------
# Tool descriptors + the full §7.4 registry
# ---------------------------------------------------------------------------
def _tool(name: str, description: str, fn: Any) -> Tool:
    """Wrap a ``(store, **args)`` callable into a :class:`Tool` (args-dict adapter)."""

    def run(store: KuzuGraphStore, args: dict[str, Any], _fn: Any = fn) -> dict[str, Any]:
        return _fn(store, **(args or {}))

    return Tool(name=name, description=description, run=run)


EXTRA_TOOLS: list[Tool] = [
    _tool(
        "resolve_entities",
        "Resolve raw mentions to canonical entity ids with ranked candidates (§7.5 N3).",
        resolve_entities,
    ),
    _tool(
        "search_material_aliases",
        "Search material entities by alias / surface form (Neo4j + catalog ids, §22).",
        search_material_aliases,
    ),
    _tool(
        "run_cypher_template",
        "Execute a named, parameterized read-only Cypher template (Mode A, §13.5).",
        run_cypher_template,
    ),
    _tool(
        "vector_search_qdrant",
        "Dense/sparse semantic search over passages with payload filters (§7.5 N6).",
        vector_search,
    ),
    _tool(
        "keyword_search_opensearch",
        "BM25 / facet lexical search over passages (§7.5 N6).",
        keyword_search,
    ),
    _tool(
        "hybrid_search",
        "RRF fusion of vector + keyword search per the §10.2 formula.",
        hybrid_search,
    ),
    _tool(
        "get_experiment_table",
        "Tabular payload of experiments (material, processing, property, value, §6.2).",
        get_experiment_table,
    ),
    _tool(
        "get_document_snippet",
        "Return a document-span fragment for inline citation (§8.3).",
        get_document_snippet,
    ),
    _tool(
        "find_graph_paths",
        "Shortest Material↔Property path between two nodes (§5.2.3 / §12.8).",
        find_graph_paths,
    ),
    _tool(
        "expand_subgraph",
        "One-/two-hop subgraph projection around seed nodes, filtered by type (§5.2.3).",
        expand_subgraph,
    ),
    _tool(
        "detect_contradictions",
        "Find conflicting measurements for the same material/regime/property (§11.1).",
        detect_contradictions,
    ),
    _tool(
        "create_review_task",
        "Draft a curation review task for low-confidence / ambiguous / conflicting facts.",
        create_review_task,
    ),
]

# The §7.4 tool names implemented directly in this module.
EXTRA_TOOL_NAMES: tuple[str, ...] = tuple(t.name for t in EXTRA_TOOLS)

# The remaining §7.4 names already served by ``agent_service.tools`` (get_evidence_by_ids
# ≈ tool_evidence_lookup; scan_gaps ≈ tool_gap_check) or wired by the parent
# (run_cypher_readonly guarded executor; build_graph_visualization_payload builder).
BASE_SPEC_TOOL_NAMES: tuple[str, ...] = (
    "run_cypher_readonly",
    "get_evidence_by_ids",
    "scan_gaps",
    "build_graph_visualization_payload",
)

# The canonical §7.4 named-tool set — exactly 16 unique names.
SPEC_7_4_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "resolve_entities",
        "search_material_aliases",
        "run_cypher_readonly",
        "run_cypher_template",
        "vector_search_qdrant",
        "keyword_search_opensearch",
        "hybrid_search",
        "get_experiment_table",
        "get_evidence_by_ids",
        "get_document_snippet",
        "find_graph_paths",
        "expand_subgraph",
        "scan_gaps",
        "detect_contradictions",
        "build_graph_visualization_payload",
        "create_review_task",
    }
)

# Full agent tool-name set (base + extended) — must equal the §7.4 set of 16.
ALL_TOOL_NAMES: tuple[str, ...] = BASE_SPEC_TOOL_NAMES + EXTRA_TOOL_NAMES

# Module invariant: the assembled set is exactly the §7.4 named-tool set.
assert set(ALL_TOOL_NAMES) == set(SPEC_7_4_TOOL_NAMES), "ALL_TOOL_NAMES must equal the §7.4 set"
assert len(ALL_TOOL_NAMES) == len(set(ALL_TOOL_NAMES)) == 16, "expected 16 unique §7.4 tool names"

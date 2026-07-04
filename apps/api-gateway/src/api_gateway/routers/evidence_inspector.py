"""Evidence Inspector provenance bundle (§17.13 / §5.2.6).

RU: Drawer доказательства уже подсвечивает цитируемый span в исходном абзаце
(``/api/v1/evidence/{id}/context``, §17.13, коммит b6f8328). Чего не хватало по
§5.2.6 — это *полей доверия* к каждому факту:

* **parsed structured object** — распарсенный структурированный объект (JSON-виджет);
* **extractor/model version** — каким прогоном/моделью извлечено (§2.1 / §6.14);
* **reviewer decision** — кто подтвердил/исправил, когда и почему (§2.1 / §12.2);
* **graph edge** — ссылка на ребро графа, сгенерированное из этого доказательства
  (клик → подсветка ребра в Graph Explorer);
* **prev/next** — навигация по соседним доказательствам в рамках ребра/сущности.

Этот роутер собирает всё это в один payload поверх *живого* графа (server-профиль,
Neo4j :8000; тот же generic ``:Node`` / ``:Rel`` model, что и Kuzu), НЕ дублируя и
НЕ переписывая существующее:

* extractor/model version переиспользует ту же логику, что и §6.14
  ``extractor_run.py`` (ребро ``EXTRACTED_BY`` приоритетнее, иначе — свойство
  ``extractor_run_id`` → узел ``:ExtractorRun``);
* graph edge находится по провенансу ребра (``r.evidence_ids`` содержит это
  доказательство) и по ребру ``SUPPORTED_BY`` (факт, который оно обосновывает);
* review-решение читается с узла доказательства (``review_status``/``verified`` +
  ``reviewed_by``/``reviewed_at``/``review_reason``), а write-эндпоинт
  ``POST /decision`` дописывает автора/причину/время БЕЗ затирания остального
  property-map (round-trip через штатный ``upsert_node``, §14.6).

Эндпоинты (prefix ``/api/v1/evidence-inspector``):

* ``GET  /{evidence_id}``            — полный provenance-бандл §5.2.6 (+ prev/next);
  опц. ``?edge_id=`` / ``?fact_id=`` задают контекст навигации.
* ``GET  /by-edge/{edge_id}``        — доказательства, сгенерировавшие ребро
  ``src|TYPE|dst`` (для клика по ребру в Graph Explorer → тот же инспектор).
* ``POST /{evidence_id}/decision``   — reviewer decision (accept/reject/needs_review)
  с автором и комментарием; roles curator/admin.

RBAC повторяет Evidence Inspector: restricted-доказательства скрыты от
непривилегированных ролей (§5.2.6).
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from api_gateway.auth import current_role
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/evidence-inspector", tags=["evidence-inspector"])

# -- RBAC (mirrors evidence.py §5.2.6) --------------------------------------- #
_PRIVILEGED = frozenset(
    {"researcher", "analyst", "project_manager", "admin", "curator"}
)
_RESTRICTED = frozenset({"internal", "restricted", "commercial_secret"})
_CURATOR = frozenset({"curator", "admin", "project_manager"})

# -- graph model constants (§8.1 / §8.2) ------------------------------------- #
_EVIDENCE = "Evidence"
_SUPPORTED_BY = "SUPPORTED_BY"
_EXTRACTED_BY = "EXTRACTED_BY"
_RUN_LABELS = ("ExtractorRun",)

# Structured-object property keys we prefer as the "parsed object" JSON widget,
# when the extractor stashed the whole parsed payload on the Evidence node.
_PARSED_KEYS = ("parsed_object", "parsed", "structured", "payload", "structured_object")

# Bookkeeping keys never echoed inside the parsed-object widget.
_SKIP_PARSED = frozenset(
    {"id", "label", "props", "_id", "_label", "text", "chunk_text"}
)

# Valid reviewer decisions (§12.2 / §5.2.6).
_DECISIONS = {"accepted", "rejected", "needs_review", "corrected"}


# --------------------------------------------------------------------------- #
# Store helpers (generic :Node / :Rel — works on Kuzu embedded + Neo4j server) #
# --------------------------------------------------------------------------- #


def _rows(cypher: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
    try:
        return get_store().rows(cypher, params or {})
    except Exception:  # pragma: no cover - store/back-end defensiveness
        return []


def _get_node(node_id: str) -> dict[str, Any] | None:
    try:
        return get_store().get_node(node_id)
    except Exception:  # pragma: no cover
        return None


def _norm_ids(val: Any) -> list[str]:
    """Normalise ``evidence_ids`` stored as a native list (Neo4j) or JSON (Kuzu)."""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x) for x in val if x]
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("["):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                return [str(x) for x in json.loads(s) if x]
        return [s] if s else []
    return []


def _restricted_denied(node: dict[str, Any], role: str) -> bool:
    return node.get("confidentiality_level") in _RESTRICTED and role not in _PRIVILEGED


# --------------------------------------------------------------------------- #
# Response models                                                              #
# --------------------------------------------------------------------------- #


class ExtractorInfo(BaseModel):
    """Which run/model produced this evidence (§6.14 / §2.1)."""

    run_id: str | None = None
    linked_via: str | None = None  # "edge" (EXTRACTED_BY) | "property" | None
    extractor: str | None = None
    model: str | None = None
    extractor_version: str | None = None
    pipeline_version: str | None = None
    prompt_version: str | None = None
    schema_version: str | None = None
    seed: Any | None = None
    created_at: str | None = None


class ReviewerDecision(BaseModel):
    """Who confirmed/corrected the evidence, and how (§2.1 / §12.2)."""

    review_status: str | None = None  # accepted | rejected | needs_review | corrected
    verified: bool | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    review_reason: str | None = None


class LinkedEdge(BaseModel):
    """A graph edge tied to this evidence — clickable to highlight in Graph Explorer."""

    edge_id: str  # "source|TYPE|target"
    source: str
    source_name: str | None = None
    target: str
    target_name: str | None = None
    type: str
    confidence: float | None = None
    relation: str  # "supported_by" (fact this evidence justifies) | "derived" (edge from evidence)


class Navigation(BaseModel):
    """prev/next within an edge or a fact's evidence set (§17.13)."""

    context: str  # "edge" | "fact" | "single"
    context_id: str | None = None
    index: int  # 0-based position of current in siblings
    total: int
    prev_id: str | None = None
    next_id: str | None = None
    sibling_ids: list[str] = []


class ProvenanceBundle(BaseModel):
    """All §5.2.6 trust fields for one Evidence node (§17.13)."""

    evidence_id: str
    found: bool
    # -- statement + source location (§5.2.6) --
    statement: str | None = None
    doc_id: str | None = None
    doc_title: str | None = None
    page: int | None = None
    table_id: str | None = None
    figure_id: str | None = None
    paragraph_id: str | None = None
    source_type: str | None = None
    evidence_strength: str | None = None
    confidence: float | None = None
    practice_type: str | None = None
    country: str | None = None
    year: int | None = None
    # -- cited span highlighted in its source chunk (§17.13, reused) --
    span: str | None = None
    chunk_text: str | None = None
    highlight_offset: int = -1
    highlight_len: int = 0
    # -- parsed structured object (JSON widget) --
    parsed_object: dict[str, Any] = {}
    # -- extractor / model version (§2.1 / §6.14) --
    extractor: ExtractorInfo = ExtractorInfo()
    # -- reviewer decision (§2.1 / §12.2) --
    reviewer: ReviewerDecision = ReviewerDecision()
    # -- graph edge(s) generated from this evidence --
    linked_edges: list[LinkedEdge] = []
    # -- prev/next navigation --
    navigation: Navigation | None = None


class EdgeEvidence(BaseModel):
    """Evidence that generated one graph edge (§17.13, Graph Explorer → inspector)."""

    edge_id: str
    source: str
    target: str
    type: str
    found: bool
    confidence: float | None = None
    evidence_ids: list[str] = []
    count: int = 0
    first: ProvenanceBundle | None = None


class DecisionBody(BaseModel):
    status: str = "accepted"  # accepted | rejected | needs_review | corrected
    reason: str = ""


class DecisionResult(BaseModel):
    evidence_id: str
    review_status: str
    verified: bool
    reviewed_by: str
    reviewed_at: str
    review_reason: str


# --------------------------------------------------------------------------- #
# Builders                                                                      #
# --------------------------------------------------------------------------- #

_CONTEXT_CYPHER = (
    "MATCH (e:Node {id:$id}) "
    "OPTIONAL MATCH (e)-[:Rel]-(c:Node {label:'Chunk'}) "
    "OPTIONAL MATCH (d:Node {label:'Document'})-[:Rel]-(c) "
    "RETURN c.text AS chunk_text, c.page AS chunk_page, d.name AS doc_title, "
    "d.country AS country, d.year AS doc_year LIMIT 1"
)


def _extractor_info(ev: dict[str, Any], evidence_id: str) -> ExtractorInfo:
    """Resolve extractor/model version — EXTRACTED_BY edge first, else prop (§6.14)."""
    run_id: str | None = None
    linked_via: str | None = None
    edge_rows = _rows(
        "MATCH (e:Node {id:$id})-[r:Rel]->(run:Node) "
        "WHERE r.type=$rt AND run.label IN $labels RETURN run.id LIMIT 1",
        {"id": evidence_id, "rt": _EXTRACTED_BY, "labels": list(_RUN_LABELS)},
    )
    if edge_rows and edge_rows[0] and edge_rows[0][0]:
        run_id = str(edge_rows[0][0])
        linked_via = "edge"
    elif ev.get("extractor_run_id"):
        run_id = str(ev["extractor_run_id"])
        linked_via = "property"

    if not run_id:
        return ExtractorInfo()

    run = _get_node(run_id)
    if run is None or run.get("label") not in _RUN_LABELS:
        return ExtractorInfo(run_id=run_id, linked_via=linked_via)
    return ExtractorInfo(
        run_id=run_id,
        linked_via=linked_via,
        extractor=run.get("extractor") or run.get("name"),
        model=run.get("model"),
        extractor_version=run.get("extractor_version"),
        pipeline_version=run.get("pipeline_version"),
        prompt_version=run.get("prompt_version"),
        schema_version=run.get("schema_version"),
        seed=run.get("seed"),
        created_at=run.get("created_at") or run.get("started_at"),
    )


def _reviewer(ev: dict[str, Any]) -> ReviewerDecision:
    verified = ev.get("verified")
    if isinstance(verified, str):
        verified = verified.lower() in {"true", "1", "yes"}
    return ReviewerDecision(
        review_status=ev.get("review_status"),
        verified=verified,
        reviewed_by=ev.get("reviewed_by") or ev.get("reviewer") or ev.get("actor"),
        reviewed_at=ev.get("reviewed_at") or ev.get("review_at"),
        review_reason=ev.get("review_reason") or ev.get("review_comment"),
    )


def _parsed_object(ev: dict[str, Any]) -> dict[str, Any]:
    """The parsed structured object for the JSON widget.

    Prefers an explicit parsed payload the extractor stashed on the node; otherwise
    echoes the node's own structured property-map (bookkeeping/large-text stripped),
    so the reader can inspect exactly what the extractor materialised (§5.2.6).
    """
    for key in _PARSED_KEYS:
        raw = ev.get(key)
        if isinstance(raw, dict) and raw:
            return raw
        if isinstance(raw, str) and raw.strip().startswith("{"):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                loaded = json.loads(raw)
                if isinstance(loaded, dict) and loaded:
                    return loaded
    return {
        k: v
        for k, v in ev.items()
        if k not in _SKIP_PARSED and v is not None
    }


def _linked_edges(evidence_id: str, fact_ids: list[str]) -> list[LinkedEdge]:
    """Edges tied to this evidence: the fact it SUPPORTED_BY + edges derived from it."""
    edges: list[LinkedEdge] = []
    seen: set[str] = set()

    # (1) SUPPORTED_BY: the fact node(s) this evidence justifies (§8.2).
    for fid in fact_ids:
        node = _get_node(fid)
        eid = f"{fid}|{_SUPPORTED_BY}|{evidence_id}"
        if eid in seen:
            continue
        seen.add(eid)
        edges.append(
            LinkedEdge(
                edge_id=eid,
                source=fid,
                source_name=(node or {}).get("name") or (node or {}).get("canonical_name"),
                target=evidence_id,
                target_name=(_get_node(evidence_id) or {}).get("name"),
                type=_SUPPORTED_BY,
                relation="supported_by",
            )
        )

    # (2) Derived edges: relationships whose r.evidence_ids contains this evidence,
    #     among edges adjacent to the fact node(s) (bounded scan, both directions).
    if fact_ids:
        rows = _rows(
            "MATCH (a:Node)-[r:Rel]->(b:Node) "
            "WHERE (a.id IN $fids OR b.id IN $fids) "
            "AND r.evidence_ids IS NOT NULL AND r.type <> $sb "
            "RETURN a.id, r.type, b.id, r.confidence, r.evidence_ids, a.name, b.name",
            {"fids": fact_ids, "sb": _SUPPORTED_BY},
        )
        for a, rtype, b, conf, eids, a_name, b_name in rows:
            if evidence_id not in _norm_ids(eids):
                continue
            eid = f"{a}|{rtype}|{b}"
            if eid in seen:
                continue
            seen.add(eid)
            edges.append(
                LinkedEdge(
                    edge_id=eid,
                    source=a,
                    source_name=a_name,
                    target=b,
                    target_name=b_name,
                    type=rtype,
                    confidence=conf,
                    relation="derived",
                )
            )
    return edges


def _fact_ids(evidence_id: str) -> list[str]:
    """Fact node(s) this evidence supports via SUPPORTED_BY (both directions)."""
    rows = _rows(
        "MATCH (e:Node {id:$id})-[r:Rel]-(f:Node) "
        "WHERE r.type=$sb AND f.label <> $ev RETURN DISTINCT f.id ORDER BY f.id",
        {"id": evidence_id, "sb": _SUPPORTED_BY, "ev": _EVIDENCE},
    )
    return [r[0] for r in rows if r and r[0]]


def _edge_evidence_ids(src: str, rtype: str, dst: str) -> list[str] | None:
    """evidence_ids of the ``src -[type]-> dst`` edge, or None if the edge is absent."""
    rows = _rows(
        "MATCH (a:Node {id:$src})-[r:Rel]->(b:Node {id:$dst}) "
        "WHERE r.type=$rt RETURN r.evidence_ids LIMIT 1",
        {"src": src, "dst": dst, "rt": rtype},
    )
    if not rows:
        return None
    return _norm_ids(rows[0][0])


def _fact_evidence_ids(fact_ids: list[str]) -> list[str]:
    """All evidence supporting the same fact(s) — ordered siblings for prev/next."""
    if not fact_ids:
        return []
    rows = _rows(
        "MATCH (f:Node)-[r:Rel]-(e:Node {label:$ev}) "
        "WHERE f.id IN $fids AND r.type=$sb RETURN DISTINCT e.id ORDER BY e.id",
        {"fids": fact_ids, "sb": _SUPPORTED_BY, "ev": _EVIDENCE},
    )
    return [r[0] for r in rows if r and r[0]]


def _navigation(
    evidence_id: str,
    fact_ids: list[str],
    edge_id: str | None,
) -> Navigation:
    """Compute prev/next siblings within an edge context or a fact's evidence set."""
    context = "single"
    context_id: str | None = None
    siblings: list[str] = []

    if edge_id:
        parts = edge_id.split("|")
        if len(parts) == 3:
            eids = _edge_evidence_ids(parts[0], parts[1], parts[2])
            if eids:
                siblings = eids
                context = "edge"
                context_id = edge_id
    if not siblings:
        siblings = _fact_evidence_ids(fact_ids)
        if siblings:
            context = "fact"
            context_id = fact_ids[0] if fact_ids else None

    if evidence_id not in siblings:
        # Always include the current evidence so index/total are coherent.
        siblings = [evidence_id, *siblings] if siblings else [evidence_id]
    idx = siblings.index(evidence_id)
    return Navigation(
        context=context,
        context_id=context_id,
        index=idx,
        total=len(siblings),
        prev_id=siblings[idx - 1] if idx > 0 else None,
        next_id=siblings[idx + 1] if idx < len(siblings) - 1 else None,
        sibling_ids=siblings,
    )


def _build_bundle(
    evidence_id: str,
    role: str,
    edge_id: str | None,
    fact_id: str | None,
) -> ProvenanceBundle:
    ev = _get_node(evidence_id)
    if ev is None:
        return ProvenanceBundle(evidence_id=evidence_id, found=False)
    if _restricted_denied(ev, role):
        raise HTTPException(status_code=403, detail="restricted evidence — access denied")

    # Span + source chunk (reuses §17.13 context logic for the highlight offset).
    span = (ev.get("text") or "").strip()
    chunk_text = ""
    title = ev.get("doc_title")
    country = ev.get("country")
    year = ev.get("source_year") or ev.get("year")
    ctx = _rows(_CONTEXT_CYPHER, {"id": evidence_id})
    if ctx and ctx[0]:
        chunk_text = ctx[0][0] or ""
        title = title or ctx[0][2]
        country = country or ctx[0][3]
        year = year or ctx[0][4]
    offset = chunk_text.find(span[:60]) if span and chunk_text else -1

    facts = _fact_ids(evidence_id)
    if fact_id and fact_id not in facts:
        facts = [fact_id, *facts]

    return ProvenanceBundle(
        evidence_id=evidence_id,
        found=True,
        statement=span or None,
        doc_id=ev.get("doc_id"),
        doc_title=title,
        page=ev.get("page"),
        table_id=ev.get("table_id") or ev.get("table"),
        figure_id=ev.get("figure_id") or ev.get("figure"),
        paragraph_id=ev.get("paragraph_id") or ev.get("chunk_id"),
        source_type=ev.get("source_type"),
        evidence_strength=ev.get("evidence_strength"),
        confidence=ev.get("confidence"),
        practice_type=ev.get("practice_type"),
        country=country,
        year=year,
        span=span or None,
        chunk_text=chunk_text or span or None,
        highlight_offset=offset,
        highlight_len=len(span) if offset >= 0 else 0,
        parsed_object=_parsed_object(ev),
        extractor=_extractor_info(ev, evidence_id),
        reviewer=_reviewer(ev),
        linked_edges=_linked_edges(evidence_id, facts),
        navigation=_navigation(evidence_id, facts, edge_id),
    )


# --------------------------------------------------------------------------- #
# Endpoints                                                                     #
# --------------------------------------------------------------------------- #


@router.get("/by-edge/{edge_id:path}", response_model=EdgeEvidence)
def evidence_by_edge(
    edge_id: str, role: str = Depends(current_role)
) -> EdgeEvidence:
    """Evidence that generated one graph edge ``source|TYPE|target`` (§17.13).

    Powers "click an edge in Graph Explorer → open the same inspector": returns the
    edge's ``evidence_ids`` (ordered for prev/next) and the full provenance bundle of
    the first one, with edge context pre-seeded so navigation stays within the edge.
    """
    parts = edge_id.split("|")
    if len(parts) != 3:
        raise HTTPException(
            status_code=400, detail="edge_id must be 'source|TYPE|target'"
        )
    src, rtype, dst = parts
    eids = _edge_evidence_ids(src, rtype, dst)
    if eids is None:
        return EdgeEvidence(
            edge_id=edge_id, source=src, target=dst, type=rtype, found=False
        )
    conf_rows = _rows(
        "MATCH (a:Node {id:$src})-[r:Rel]->(b:Node {id:$dst}) "
        "WHERE r.type=$rt RETURN r.confidence LIMIT 1",
        {"src": src, "dst": dst, "rt": rtype},
    )
    conf = conf_rows[0][0] if conf_rows and conf_rows[0] else None
    first: ProvenanceBundle | None = None
    if eids:
        first = _build_bundle(eids[0], role, edge_id=edge_id, fact_id=None)
    return EdgeEvidence(
        edge_id=edge_id,
        source=src,
        target=dst,
        type=rtype,
        found=True,
        confidence=conf,
        evidence_ids=eids,
        count=len(eids),
        first=first,
    )


@router.post("/{evidence_id:path}/decision", response_model=DecisionResult)
def record_decision(
    evidence_id: str,
    body: DecisionBody,
    role: str = Depends(current_role),
    x_user: str = Header(default="curator"),
) -> DecisionResult:
    """Record a reviewer decision with author + comment + timestamp (§2.1 / §12.2).

    Stamps ``review_status``/``verified`` plus ``reviewed_by``/``reviewed_at``/
    ``review_reason`` WITHOUT clobbering the rest of the node's property-map: the
    existing map is read and round-tripped through the store's ``upsert_node`` (no raw
    write-Cypher, §14.6). Roles curator/admin/project_manager only.
    """
    if role not in _CURATOR:
        raise HTTPException(status_code=403, detail="curator role required")
    status = body.status.strip().lower()
    if status not in _DECISIONS:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {sorted(_DECISIONS)}",
        )
    store = get_store()
    ev = _get_node(evidence_id)
    if ev is None or ev.get("label") != _EVIDENCE:
        raise HTTPException(status_code=404, detail="evidence not found")

    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()
    verified = status in {"accepted", "corrected"}
    # Round-trip the existing property-map so nothing else is lost (Kuzu rewrites the
    # props JSON column wholesale on upsert; Neo4j does SET n += props).
    merged: dict[str, Any] = {
        k: v for k, v in ev.items() if k not in ("id", "label")
    }
    merged.update(
        review_status=status,
        verified=verified,
        reviewed_by=x_user,
        reviewed_at=now,
        review_reason=body.reason,
    )
    store.upsert_node(evidence_id, _EVIDENCE, **merged)
    return DecisionResult(
        evidence_id=evidence_id,
        review_status=status,
        verified=verified,
        reviewed_by=x_user,
        reviewed_at=now,
        review_reason=body.reason,
    )


@router.get("/{evidence_id:path}", response_model=ProvenanceBundle)
def provenance_bundle(
    evidence_id: str,
    role: str = Depends(current_role),
    edge_id: str | None = Query(default=None),
    fact_id: str | None = Query(default=None),
) -> ProvenanceBundle:
    """Full §5.2.6 provenance bundle for one Evidence node (§17.13).

    Returns everything the Evidence Inspector needs to make a fact *trustable*: the
    extracted statement, source location (doc/page/table/figure/paragraph), the cited
    span with its highlight offset in the source chunk, the parsed structured object,
    the extractor/model version that produced it, the reviewer decision, the graph
    edge(s) generated from it, and prev/next navigation within the edge/fact.
    """
    return _build_bundle(evidence_id, role, edge_id=edge_id, fact_id=fact_id)

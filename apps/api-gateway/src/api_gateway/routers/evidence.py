"""Evidence inspector (§3.6 / §5.2.6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from api_gateway.auth import current_role
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])

_PRIVILEGED = {"researcher", "analyst", "project_manager", "admin", "curator"}
_RESTRICTED = {"internal", "restricted", "commercial_secret"}
_CURATOR = {"curator", "admin"}


class AssembleBody(BaseModel):
    node_ids: list[str]
    max_per_claim: int = 5


@router.post("/assemble")
def assemble(body: AssembleBody, role: str = Depends(current_role)) -> dict:
    """Assemble numbered, deduplicated citations for a set of fact nodes (§13.14)."""
    from agent_service.evidence_assembler import assemble_evidence

    result = assemble_evidence(get_store(), body.node_ids, max_per_claim=body.max_per_claim)
    return result.as_dict()


@router.get("/by-node/{node_id}")
def evidence_by_node(node_id: str, role: str = Depends(current_role)) -> dict:
    """All evidence supporting a fact node — the Evidence Inspector source list (§5.2.6)."""
    store = get_store()
    rows = store.rows(
        "MATCH (f:Node {id:$id})-[:Rel {type:'SUPPORTED_BY'}]->(e:Node {label:'Evidence'}) "
        "RETURN e.id, e.doc_id, e.page, e.text, e.evidence_strength, e.confidence",
        {"id": node_id},
    )
    items = [
        {
            "evidence_id": r[0],
            "doc_id": r[1],
            "page": r[2],
            "text": r[3],
            "evidence_strength": r[4],
            "confidence": r[5],
        }
        for r in rows
    ]
    return {"node_id": node_id, "count": len(items), "evidence": items}


class ReviewBody(BaseModel):
    status: str = "accepted"  # accepted | rejected
    reason: str = ""


@router.post("/{evidence_id}/review")
def review_evidence(
    evidence_id: str,
    body: ReviewBody,
    role: str = Depends(current_role),
    x_user: str = Header(default="curator"),
) -> dict:
    """Curator verifies/rejects an evidence span (§12.2/§5.2.6)."""
    if role not in _CURATOR:
        raise HTTPException(status_code=403, detail="curator role required")
    store = get_store()
    nd = store.get_node(evidence_id)
    if nd is None or nd.get("label") != "Evidence":
        raise HTTPException(status_code=404, detail="evidence not found")
    store.upsert_node(
        evidence_id, "Evidence", review_status=body.status, verified=(body.status == "accepted")
    )
    return {"evidence_id": evidence_id, "review_status": body.status, "actor": x_user}


_CONTEXT_CYPHER = (
    "MATCH (e:Node {id:$id}) "
    "OPTIONAL MATCH (e)-[:Rel]-(c:Node {label:'Chunk'}) "
    "OPTIONAL MATCH (d:Node {label:'Document'})-[:Rel]-(c) "
    "RETURN c.text AS chunk_text, c.page AS chunk_page, d.name AS doc_title, "
    "d.country AS country, d.year AS doc_year LIMIT 1"
)


@router.get("/{evidence_id}/context")
def evidence_context(evidence_id: str, role: str = Depends(current_role)) -> dict:
    """Evidence span + its surrounding source chunk (with a highlight offset) + doc meta.

    Powers the Evidence Inspector (§17.13): the researcher sees the cited span
    highlighted in the actual paragraph it came from, with source provenance.
    """
    store = get_store()
    nd = store.get_node(evidence_id)
    if nd is None:
        raise HTTPException(status_code=404, detail="evidence not found")
    if nd.get("confidentiality_level") in _RESTRICTED and role not in _PRIVILEGED:
        raise HTTPException(status_code=403, detail="restricted evidence — access denied")

    span = (nd.get("text") or "").strip()
    chunk_text = ""
    title = country = None
    year = nd.get("source_year") or nd.get("year")
    rows = store.rows(_CONTEXT_CYPHER, {"id": evidence_id})
    if rows:
        chunk_text = rows[0][0] or ""
        title = rows[0][2]
        country = rows[0][3] or nd.get("country")
        year = year or rows[0][4]
    # Offset of the span within its chunk (for client-side highlighting); -1 if absent.
    offset = chunk_text.find(span[:60]) if span and chunk_text else -1
    return {
        "evidence_id": nd["id"],
        "span": span,
        "chunk_text": chunk_text or span,
        "highlight_offset": offset,
        "highlight_len": len(span) if offset >= 0 else 0,
        "doc_id": nd.get("doc_id"),
        "doc_title": title,
        "page": nd.get("page"),
        "practice_type": nd.get("practice_type"),
        "country": country,
        "year": year,
        "evidence_strength": nd.get("evidence_strength"),
        "confidence": nd.get("confidence"),
    }


@router.get("/{evidence_id}")
def get_evidence(evidence_id: str, role: str = Depends(current_role)) -> dict:
    nd = get_store().get_node(evidence_id)
    if nd is None:
        raise HTTPException(status_code=404, detail="evidence not found")
    # RBAC: non-privileged roles cannot read restricted evidence (finding evidence.py:14)
    if nd.get("confidentiality_level") in _RESTRICTED and role not in _PRIVILEGED:
        raise HTTPException(status_code=403, detail="restricted evidence — access denied")
    return {
        "evidence_id": nd["id"],
        "doc_id": nd.get("doc_id"),
        "page": nd.get("page"),
        "text": nd.get("text"),
        "source_type": nd.get("source_type"),
        "evidence_strength": nd.get("evidence_strength"),
        "confidence": nd.get("confidence"),
        "review_status": nd.get("review_status"),
        "practice_type": nd.get("practice_type"),
        "year": nd.get("year"),
    }

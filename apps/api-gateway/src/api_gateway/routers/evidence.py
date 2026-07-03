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
        {"evidence_id": r[0], "doc_id": r[1], "page": r[2], "text": r[3],
         "evidence_strength": r[4], "confidence": r[5]}
        for r in rows
    ]
    return {"node_id": node_id, "count": len(items), "evidence": items}


class ReviewBody(BaseModel):
    status: str = "accepted"  # accepted | rejected
    reason: str = ""


@router.post("/{evidence_id}/review")
def review_evidence(
    evidence_id: str, body: ReviewBody, role: str = Depends(current_role),
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

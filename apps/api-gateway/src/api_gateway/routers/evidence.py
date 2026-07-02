"""Evidence inspector (§3.6 / §5.2.6)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])


@router.get("/{evidence_id}")
def get_evidence(evidence_id: str) -> dict:
    nd = get_store().get_node(evidence_id)
    if nd is None:
        raise HTTPException(status_code=404, detail="evidence not found")
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

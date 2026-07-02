"""Technology comparison endpoint (§24.13)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api_gateway.auth import current_role
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1", tags=["comparison"])


class ComparisonRequest(BaseModel):
    query: str


@router.post("/comparison")
def comparison(req: ComparisonRequest, role: str = Depends(current_role)) -> dict:
    from agent_service.comparison import build_comparison

    return build_comparison(req.query, get_store(), role=role)

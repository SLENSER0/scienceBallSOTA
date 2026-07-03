"""Agentic Technology Advisor endpoints (§13 / demo flagship).

Runs the multi-agent :mod:`agent_service.advisor` — one reasoning agent per candidate
technology (GLM-5.2, in parallel) + a synthesis agent (DeepSeek-V4-Flash) — over the
live graph. ``/advise`` returns the ranked recommendation as one payload; ``/advise/stream``
streams each candidate card the instant its agent finishes, as typed SSE (§5.3), so the
UI shows the agents reasoning live.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api_gateway import audit
from api_gateway.auth import current_role, current_user
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/advise", tags=["advisor"])


class AdviseBody(BaseModel):
    query: str
    geography: str | None = None  # russia | cis | foreign | global | all | None
    top_k: int = 5


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n".encode()


@router.post("")
def advise(
    body: AdviseBody,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """Full multi-agent recommendation for the given constraints (§ agentic advisor)."""
    if not body.query.strip():
        raise HTTPException(status_code=422, detail="query is required")
    from agent_service.advisor import advise as run_advise

    audit.record(
        "advise", user=user, role=role, detail={"q": body.query[:160], "geo": body.geography}
    )
    result = run_advise(body.query, get_store(), geography=body.geography, top_k=body.top_k)
    return result.as_dict()


@router.get("/stream")
def advise_stream(
    query: str = Query(min_length=1),
    geography: str | None = None,
    top_k: int = 5,
    role: str = Depends(current_role),
) -> StreamingResponse:
    """Stream the advisory as SSE: constraints → each candidate card → summary → done."""
    from agent_service.advisor import stream_advise

    def gen() -> Iterator[bytes]:
        try:
            for event, data in stream_advise(query, get_store(), geography=geography, top_k=top_k):
                yield _sse(event, data)
        except Exception as exc:  # surface a failure mid-stream instead of a dead connection
            yield _sse("error", {"message": str(exc)[:200]})

    return StreamingResponse(gen(), media_type="text/event-stream")

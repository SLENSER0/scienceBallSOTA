"""Agentic insight endpoints — командный центр + карта пробелов.

- ``GET /insights/briefing`` runs the analyst agent (:mod:`agent_service.briefing`) to
  turn a whole-graph snapshot into a narrative «state of knowledge» briefing.
- ``GET /insights/gaps-prioritized`` fans out prioritization agents
  (:mod:`agent_service.gap_prioritizer`) to rank the open gaps into a research backlog.

Distinct ``/insights`` prefix so neither collides with the existing ``/gaps`` router.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from api_gateway.auth import current_role
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/insights", tags=["insights"])


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n".encode()


@router.get("/briefing")
def briefing(_role: str = Depends(current_role)) -> dict:
    """Agent-written «state of knowledge» briefing + the underlying snapshot."""
    from agent_service.briefing import generate_briefing

    return generate_briefing(get_store())


@router.get("/gaps-prioritized")
def gaps_prioritized(limit: int = 12, _role: str = Depends(current_role)) -> dict:
    """Agentically prioritized research backlog over the open gaps."""
    from agent_service.gap_prioritizer import prioritize_gaps

    return prioritize_gaps(get_store(), limit=limit)


@router.get("/gaps-prioritized/stream")
def gaps_prioritized_stream(
    limit: int = Query(14, ge=1, le=24), _role: str = Depends(current_role)
) -> StreamingResponse:
    """Stream each gap as its scoring agent finishes — honest done/total (10 in parallel)."""
    from agent_service.gap_prioritizer import stream_prioritize_gaps

    def gen() -> Iterator[bytes]:
        try:
            for event, data in stream_prioritize_gaps(get_store(), limit=limit):
                yield _sse(event, data)
        except Exception as exc:  # surface a mid-stream failure instead of a dead socket
            yield _sse("error", {"message": str(exc)[:200]})

    return StreamingResponse(gen(), media_type="text/event-stream")

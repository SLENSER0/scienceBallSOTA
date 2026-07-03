"""Agentic insight endpoints — командный центр + карта пробелов.

- ``GET /insights/briefing`` runs the analyst agent (:mod:`agent_service.briefing`) to
  turn a whole-graph snapshot into a narrative «state of knowledge» briefing.
- ``GET /insights/gaps-prioritized`` fans out prioritization agents
  (:mod:`agent_service.gap_prioritizer`) to rank the open gaps into a research backlog.

Distinct ``/insights`` prefix so neither collides with the existing ``/gaps`` router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api_gateway.auth import current_role
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/insights", tags=["insights"])


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

"""Query-time entity resolution API (§8.8 ``POST /api/v1/entities/resolve``).

Exposes the §8.8 ``resolve_mention`` cascade
(:mod:`api_gateway.mention_resolver`) over HTTP so the agent's grounding node
(§7.6 Node 3) and the UI can turn a raw surface form into a canonical entity id
with a confidence and ranked alternatives:

    exact alias → Neo4j fulltext (``entity_name_index``)
                → vector search (``entity_embedding_index``) → Splink scoring

* ``POST /api/v1/entities/resolve``  body ``{ text, entity_type?, limit? }`` —
  resolves one mention, returns the §7.3 ``EntityMention`` + ``candidates[]``.
* ``POST /api/v1/entities/resolve/batch`` body ``{ mentions[], entity_type? }``
  — the agent's ``resolve_entities`` tool shape (§7.4): resolves many at once.

Read-only — no curator role, no graph mutation (§8.8: "read-only, без
curator-роли"). The simple alias-only ``GET /api/v1/entities/resolve`` already
lives in ``routers/search.py``; this POST path is the full cascade the spec
marks optional-but-recommended, and coexists with the GET by HTTP method.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api_gateway.deps import get_store
from api_gateway.mention_resolver import resolve_mention

router = APIRouter(prefix="/api/v1/entities", tags=["entities"])


class ResolveRequest(BaseModel):
    text: str = Field(..., min_length=1, description="raw surface form / упоминание")
    entity_type: str | None = Field(
        default=None, description="optional label constraint, e.g. 'Material'"
    )
    limit: int = Field(default=5, ge=1, le=25, description="max ranked candidates")


class CandidateScores(BaseModel):
    alias: float = 0.0
    fulltext: float = 0.0
    vector: float = 0.0
    splink: float = 0.0


class ResolvedCandidate(BaseModel):
    entity_id: str
    name: str | None = None
    label: str | None = None
    confidence: float
    scores: CandidateScores


class EntityMentionResponse(BaseModel):
    """§7.3 EntityMention + ranked candidates (superset)."""

    text: str
    canonical_id: str | None
    entity_type: str | None
    confidence: float
    tier: str
    name: str | None = None
    candidates: list[ResolvedCandidate]


class BatchResolveRequest(BaseModel):
    mentions: list[str] = Field(..., min_length=1, max_length=64)
    entity_type: str | None = None
    limit: int = Field(default=5, ge=1, le=25)


class BatchResolveResponse(BaseModel):
    count: int
    mentions: list[EntityMentionResponse]


def _to_response(payload: dict[str, Any]) -> EntityMentionResponse:
    return EntityMentionResponse(**payload)


@router.post("/resolve", response_model=EntityMentionResponse)
def resolve(req: ResolveRequest) -> EntityMentionResponse:
    """Resolve one mention through the full §8.8 cascade (read-only)."""
    store = get_store()
    mention = resolve_mention(store, req.text, req.entity_type, limit=req.limit)
    return _to_response(mention.as_dict())


@router.post("/resolve/batch", response_model=BatchResolveResponse)
def resolve_batch(req: BatchResolveRequest) -> BatchResolveResponse:
    """Resolve many mentions — the agent ``resolve_entities`` tool shape (§7.4)."""
    store = get_store()
    out = [
        _to_response(
            resolve_mention(store, text, req.entity_type, limit=req.limit).as_dict()
        )
        for text in req.mentions
    ]
    return BatchResolveResponse(count=len(out), mentions=out)

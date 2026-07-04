"""ER candidate review API (§8.8 / §6.2 /entities/*).

Surfaces the Splink entity-resolution output (§9.2 Step 6) as reviewable
candidates: ``GET /api/v1/entities/candidates?status=review_needed&type=`` runs
the deterministic/Splink ER pipeline (:func:`kg_er.resolve`) over canonical
entity nodes pulled from the live graph store, then returns the resulting merge
proposals in the ``ERDecision`` shape (``candidate_id, mentions,
match_probability, decision``) so the review screen can show each group's
mentions, probability and auto/review/separate decision and drive a Merge.

This is a read-only endpoint; the Merge action itself goes through the existing
``POST /api/v1/entities/merge`` (curation-service, §8.9). We compute candidates
on demand rather than persisting them, so the screen reflects the current graph.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/entities", tags=["entities"])

# kg_er entity types that have a feature builder / Splink spec (§8.4).
_SUPPORTED_TYPES = ("Material", "Alloy", "Equipment", "Person", "Lab", "ResearchTeam")
_VALID_STATUS = ("auto_merge", "review_needed", "separate", "all")

# Cap how many nodes we feed the resolver per request — keeps latency bounded and
# stays on the deterministic scoring path for typical graph sizes.
_MAX_NODES = 400


class MentionRef(BaseModel):
    id: str
    name: str | None = None
    label: str | None = None
    formula: str | None = None
    review_status: str | None = None


class ERCandidate(BaseModel):
    """One ER decision group in §9.2 Step 6 shape."""

    candidate_id: str
    entity_type: str
    decision: str
    match_probability: float
    canonical_id: str
    blocked_by_review: bool
    mentions: list[MentionRef]


class ERCandidatesResponse(BaseModel):
    status: str
    entity_type: str
    count: int
    candidates: list[ERCandidate]


def _candidate_id(entity_type: str, members: tuple[str, ...]) -> str:
    """Stable id for a merge group (order-independent) so the UI can key on it."""
    digest = hashlib.sha1("|".join(sorted(members)).encode("utf-8")).hexdigest()[:12]
    return f"cand:{entity_type.lower()}:{digest}"


def _mention_dicts(store: Any, entity_type: str) -> list[dict[str, Any]]:
    """Pull canonical nodes of *entity_type* as ER mention records (`unique_id`)."""
    rows = store.rows(
        "MATCH (n:Node) WHERE n.label = $label AND n.name IS NOT NULL "
        "RETURN n LIMIT $cap",
        {"label": entity_type, "cap": _MAX_NODES},
    )
    mentions: list[dict[str, Any]] = []
    for r in rows:
        nd = store._node_dict(r[0])
        nid = nd.get("id")
        if not nid:
            continue
        mentions.append(
            {
                "unique_id": nid,
                "name": nd.get("name") or nd.get("canonical_name"),
                "formula": nd.get("formula") or nd.get("normalized_formula"),
                "designation": nd.get("designation") or nd.get("designation_code"),
                "alloy_family": nd.get("alloy_family"),
                "manufacturer": nd.get("manufacturer"),
                "model": nd.get("model") or nd.get("model_code"),
                "equipment_class": nd.get("equipment_class"),
                "orcid": nd.get("orcid"),
                "email": nd.get("email"),
                "org": nd.get("org") or nd.get("organization"),
                "city": nd.get("city"),
                "country": nd.get("country"),
                # kept for the mention card the UI renders
                "_label": nd.get("label"),
                "_review_status": nd.get("review_status"),
            }
        )
    return mentions


@router.get("/candidates", response_model=ERCandidatesResponse)
def er_candidates(
    status: str = Query(default="review_needed"),
    type: str = Query(default="Material"),
    limit: int = Query(default=50, ge=1, le=200),
) -> ERCandidatesResponse:
    """List ER merge candidates for review (§8.8).

    Runs :func:`kg_er.resolve` over the current canonical nodes of *type* and
    returns the proposals whose decision matches *status* (``all`` = any).
    """
    entity_type = type if type in _SUPPORTED_TYPES else "Material"
    want = status if status in _VALID_STATUS else "review_needed"

    store = get_store()
    mentions = _mention_dicts(store, entity_type)
    by_id = {m["unique_id"]: m for m in mentions}

    candidates: list[ERCandidate] = []
    if len(mentions) >= 2:
        from kg_er import resolve  # lazy: heavy Splink/duckdb import

        # reviewed/verified canonicals are protected from silent auto-merge (§8.9)
        reviewed = frozenset(
            m["unique_id"]
            for m in mentions
            if m.get("_review_status") in {"accepted", "corrected"}
        )
        try:
            result = resolve(entity_type, mentions, reviewed_ids=reviewed)
            proposals = result.proposals
        except Exception:  # pragma: no cover - ER must never 500 the review screen
            proposals = []

        for p in proposals:
            if want != "all" and p.decision.value != want:
                continue
            refs = []
            for mid in p.members:
                src = by_id.get(mid, {})
                refs.append(
                    MentionRef(
                        id=mid,
                        name=src.get("name"),
                        label=src.get("_label") or entity_type,
                        formula=src.get("formula"),
                        review_status=src.get("_review_status"),
                    )
                )
            candidates.append(
                ERCandidate(
                    candidate_id=_candidate_id(entity_type, p.members),
                    entity_type=entity_type,
                    decision=p.decision.value,
                    match_probability=round(p.probability, 4),
                    canonical_id=p.canonical_id,
                    blocked_by_review=p.blocked_by_review,
                    mentions=refs,
                )
            )

    # Highest-probability groups first — the most confident merges rise to the top.
    candidates.sort(key=lambda c: c.match_probability, reverse=True)
    candidates = candidates[:limit]
    return ERCandidatesResponse(
        status=want,
        entity_type=entity_type,
        count=len(candidates),
        candidates=candidates,
    )

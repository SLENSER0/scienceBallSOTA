"""Close the loop from the arbiter UI (§16.6) — resolve a contradiction by accepting a side.

The agentic arbiter (:mod:`agent_service.contradiction_analysis`, ``/api/v1/arbiter``) is
read-only: it reasons over each side's provenance and returns a verdict. This router is the
*human-in-the-loop* superstructure on top of it — it lets a curator commit the arbiter's
call into the graph:

* ``GET  /api/v1/arbiter/{cid}/candidates`` — the conflicting sides with a stable
  ``claim_id`` (the Measurement node id) and a deterministic ``support`` score; the
  best-supported side is flagged ``likely_correct`` so the UI can offer a single
  «принять likely-correct сторону» button.
* ``POST /api/v1/arbiter/{cid}/resolve`` — commit a winning side: the ``Contradiction``
  node flips to ``review_status="resolved"`` with ``resolution=<winner claim_id>``, every
  ``CONTRADICTS`` edge touching a losing side is *quenched* (``contradicted=false``), and a
  ``CurationEvent{action:"resolve_contradiction"}`` is recorded — a real human decision, not
  a read-only verdict.

Reuses the pure planner :func:`kg_common.storage.contradiction_resolution.plan_resolution`
(state transition + quench list) and :meth:`curation_service.CurationService.resolve_contradiction`
(status flip + CurationEvent) — nothing here re-implements graph mutation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from api_gateway.auth import current_role
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/arbiter", tags=["contradictions"])

# Sides of a contradiction, keyed by the Measurement node id, with provenance and the
# count of supporting Evidence nodes — enough to score which side is best supported.
_CANDIDATES_CYPHER = (
    "MATCH (c:Node {id:$cid})-[:Rel]-(m:Node {label:'Measurement'}) "
    "OPTIONAL MATCH (m)-[:Rel]-(e:Node {label:'Evidence'}) "
    "RETURN m.id AS mid, m.value_normalized AS val, m.normalized_unit AS unit, "
    "m.property_name AS prop, m.practice_type AS practice, m.source_year AS year, "
    "m.country AS country, m.confidence AS conf, "
    "collect(DISTINCT e.text)[0] AS text, count(DISTINCT e) AS ev_count "
    "ORDER BY mid LIMIT 12"
)

# Directed CONTRADICTS edges touching any of the contradiction's claims (one row per edge).
_CONTRADICTS_EDGES_CYPHER = (
    "MATCH (a:Node)-[r:Rel {type:'CONTRADICTS'}]->(b:Node) "
    "WHERE a.id IN $ids OR b.id IN $ids "
    "RETURN a.id AS s, b.id AS t"
)

# Quench CONTRADICTS edges whose either endpoint is a losing claim.
_QUENCH_CYPHER = (
    "MATCH (a:Node)-[r:Rel {type:'CONTRADICTS'}]-(b:Node) "
    "WHERE a.id IN $losers OR b.id IN $losers "
    "SET r.contradicted = false, r.quenched = true, "
    "r.quenched_by = $ev, r.quenched_at = $at "
    "RETURN count(r) AS n"
)


def _support(conf: Any, ev_count: Any, year: Any) -> float:
    """Deterministic support score for a side — confidence + evidence + recency.

    No LLM call: the «likely-correct» flag must be stable and available even when the
    arbiter agent is offline. Confidence dominates; supporting evidence and a recent
    vintage break ties.
    """
    try:
        c = float(conf) if conf is not None else 0.5
    except (TypeError, ValueError):
        c = 0.5
    ev = min(int(ev_count or 0), 3) * 0.1
    rec = 0.0
    try:
        if year is not None:
            rec = max(0.0, min((int(year) - 2000) / 50.0, 0.4))
    except (TypeError, ValueError):
        rec = 0.0
    return round(c + ev + rec, 4)


def _candidates(store: Any, cid: str) -> list[dict[str, Any]]:
    """Load the conflicting sides with a stable claim_id + support score."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in store.rows(_CANDIDATES_CYPHER, {"cid": cid}):
        mid = r[0]
        if not mid or mid in seen:
            continue
        seen.add(mid)
        out.append(
            {
                "claim_id": mid,
                "value": r[1],
                "unit": r[2],
                "property": r[3],
                "practice": r[4],
                "year": r[5],
                "country": r[6],
                "confidence": r[7],
                "evidence": (r[8] or "")[:280] or None,
                "evidence_count": r[9] or 0,
                "support": _support(r[7], r[9], r[5]),
            }
        )
    if out:
        best = max(out, key=lambda s: s["support"])
        for s in out:
            s["likely_correct"] = s["claim_id"] == best["claim_id"]
    return out


def _contradicts_edges(store: Any, claim_ids: list[str]) -> list[str]:
    """Synthetic ids (``src|CONTRADICTS|dst``) of CONTRADICTS edges among the claims."""
    if not claim_ids:
        return []
    rows = store.rows(_CONTRADICTS_EDGES_CYPHER, {"ids": claim_ids})
    return [f"{r[0]}|CONTRADICTS|{r[1]}" for r in rows if r[0] and r[1]]


class ResolveBody(BaseModel):
    """Accept a winning side. ``winner_claim_id`` omitted → take the likely-correct side."""

    winner_claim_id: str | None = None
    reason: str = ""


@router.get("/{cid:path}/candidates")
def candidates(cid: str, _role: str = Depends(current_role)) -> dict:
    """List the contradiction's sides with claim ids and the likely-correct flag."""
    store = get_store()
    node = store.get_node(cid)
    if node is None or node.get("label") != "Contradiction":
        raise HTTPException(status_code=404, detail="contradiction not found")
    cands = _candidates(store, cid)
    likely = next((c["claim_id"] for c in cands if c.get("likely_correct")), None)
    return {
        "id": cid,
        "name": node.get("name") or cid,
        "status": node.get("review_status"),
        "resolution": node.get("resolution"),
        "candidates": cands,
        "likely_correct_id": likely,
    }


@router.post("/{cid:path}/resolve")
def resolve(
    cid: str,
    body: ResolveBody,
    _role: str = Depends(current_role),
    x_user: str = Header(default="curator"),
) -> dict:
    """Commit a winning side: Contradiction → resolved, quench losers, write CurationEvent."""
    from curation_service.curation import CurationService

    from kg_common.storage.contradiction_resolution import plan_resolution

    store = get_store()
    node = store.get_node(cid)
    if node is None or node.get("label") != "Contradiction":
        raise HTTPException(status_code=404, detail="contradiction not found")

    cands = _candidates(store, cid)
    claim_ids = [c["claim_id"] for c in cands]
    if not claim_ids:
        raise HTTPException(status_code=422, detail="no comparable sides to resolve")

    winner = body.winner_claim_id or next(
        (c["claim_id"] for c in cands if c.get("likely_correct")), None
    )
    if winner not in claim_ids:
        raise HTTPException(
            status_code=422,
            detail=f"winner {winner!r} is not one of this contradiction's sides",
        )

    reason = body.reason or f"accepted likely-correct side {winner}"
    edges = _contradicts_edges(store, claim_ids)
    plan = plan_resolution({"id": cid, "claim_ids": claim_ids, "contradicts_edges": edges},
                           winner_claim_id=winner, reason=reason)

    # Status flip + CurationEvent — reuse the existing §16.6 handler (one path, audited).
    svc = CurationService(store)
    try:
        event = svc.resolve_contradiction(cid, resolution=winner, actor=x_user, reason=reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="contradiction not found") from exc

    # Quench CONTRADICTS edges touching a losing side (the arbiter-specific extra).
    quenched = 0
    if plan.loser_claim_ids:
        qrows = store.rows(
            _QUENCH_CYPHER,
            {
                "losers": list(plan.loser_claim_ids),
                "ev": event["event_id"],
                "at": datetime.now(UTC).isoformat(),
            },
        )
        quenched = int(qrows[0][0]) if qrows and qrows[0] else 0

    return {
        "event": event,
        "winner_claim_id": winner,
        "loser_claim_ids": list(plan.loser_claim_ids),
        "quenched_edges": quenched,
        "status": "resolved",
        "resolution": winner,
    }

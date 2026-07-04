"""Source trust / retractions / freshness surface for citations + verifier (§23.27).

Fuses the already-shipped trust/freshness/retraction engines
(:mod:`kg_retrievers.citation_trust`) into HTTP so the chat answer view can:

* ``POST /api/v1/source-trust/assess`` — score an answer's citations, roll them
  up into warnings («источник отозван / устарел / непроверен») and return a
  **verifier-adjusted confidence** (lowered when a primary support is
  retracted/superseded/stale). Per-citation metadata missing from the request is
  enriched from the graph store (year → age, ``evidence_strength`` → peer-review,
  ``props.retracted`` / ``props.source_status`` → status).
* ``GET  /api/v1/source-trust/source/{doc_id}`` — the trust card for one source.
* ``GET  /api/v1/source-trust/demo`` — a canned active+stale+retracted scenario
  so the UI (and the §23.27 acceptance demo) has data with no ingest.

All scoring lives in the pure :mod:`kg_retrievers.citation_trust` module; this
router only does HTTP, store lookup and the merge of request-supplied overrides
on top of store-derived source metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api_gateway.auth import current_role
from api_gateway.deps import get_store
from kg_retrievers.citation_trust import assess_answer, assess_citation

router = APIRouter(prefix="/api/v1/source-trust", tags=["source-trust"])


# --------------------------------------------------------------------------- #
# Request models                                                              #
# --------------------------------------------------------------------------- #


class CitationIn(BaseModel):
    """One citation the answer relies on — overrides win over store metadata."""

    doc_id: str
    source_status: str | None = None  # active|corrected|retracted|superseded|deprecated
    age_days: float | None = None
    peer_reviewed: bool | None = None
    citation_count: int | None = None
    primary: bool = False


class AssessRequest(BaseModel):
    citations: list[CitationIn] = Field(default_factory=list)
    base_confidence: float = 1.0


# --------------------------------------------------------------------------- #
# Store enrichment — read per-source metadata from the graph                   #
# --------------------------------------------------------------------------- #

_PEER_STRENGTHS = frozenset({"peer_reviewed", "peer-reviewed", "peerreviewed"})
_APPROX_DAYS_PER_YEAR = 365.25


def _source_meta_from_store(doc_id: str) -> dict[str, Any]:
    """Best-effort source metadata from the graph node ``doc_id`` (§23.27).

    Reads the flattened node (columns + JSON ``props`` catch-all) and derives:
    ``source_status`` (explicit prop, or ``retracted`` when the soft-retraction
    tombstone is set), ``age_days`` (from ``year``), ``peer_reviewed`` (from
    ``evidence_strength`` / ``review_status``) and ``citation_count`` (prop).
    Returns an empty dict when the node is unknown — the caller falls back to
    request overrides / defaults.
    """
    try:
        node = get_store().get_node(doc_id)
    except Exception:  # pragma: no cover - store defensiveness
        node = None
    if not node:
        return {}

    meta: dict[str, Any] = {}

    # source_status: explicit prop, else infer from the retraction tombstone.
    status = node.get("source_status")
    if not status and node.get("retracted") is True:
        status = "retracted"
    if status:
        meta["source_status"] = str(status)

    # age_days from publication year (best-effort).
    year = node.get("year")
    if isinstance(year, int) and year > 0:
        now_year = datetime.now(UTC).year
        meta["age_days"] = max(0.0, (now_year - year) * _APPROX_DAYS_PER_YEAR)

    # peer-review from evidence_strength / review_status.
    strength = str(node.get("evidence_strength") or "").strip().lower()
    review = str(node.get("review_status") or "").strip().lower()
    if strength in _PEER_STRENGTHS or review == "accepted":
        meta["peer_reviewed"] = True

    cc = node.get("citation_count")
    if isinstance(cc, int):
        meta["citation_count"] = cc

    return meta


def _merge_citation(cit: CitationIn) -> dict[str, Any]:
    """Store metadata for ``doc_id`` with request overrides layered on top."""
    merged = _source_meta_from_store(cit.doc_id)
    merged["doc_id"] = cit.doc_id
    merged["primary"] = cit.primary
    if cit.source_status is not None:
        merged["source_status"] = cit.source_status
    if cit.age_days is not None:
        merged["age_days"] = cit.age_days
    if cit.peer_reviewed is not None:
        merged["peer_reviewed"] = cit.peer_reviewed
    if cit.citation_count is not None:
        merged["citation_count"] = cit.citation_count
    return merged


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


@router.post("/assess")
def assess(req: AssessRequest, _role: str = Depends(current_role)) -> dict[str, Any]:
    """Assess an answer's citations → warnings + verifier-adjusted confidence (§23.27).

    Returns the :class:`~kg_retrievers.citation_trust.AnswerTrustReport` roll-up:
    per-citation trust/freshness verdicts, de-duplicated warnings and an
    ``adjusted_confidence`` the verifier lowered for retracted/stale/unreviewed
    primary sources.
    """
    merged = [_merge_citation(c) for c in req.citations]
    report = assess_answer(merged, base_confidence=req.base_confidence)
    return report.as_dict()


@router.get("/source/{doc_id:path}")
def source_card(doc_id: str, _role: str = Depends(current_role)) -> dict[str, Any]:
    """Trust / freshness / retraction card for a single source (§23.27)."""
    meta = _source_meta_from_store(doc_id)
    meta["doc_id"] = doc_id
    return assess_citation(meta).as_dict()


@router.get("/demo")
def demo(_role: str = Depends(current_role)) -> dict[str, Any]:
    """Canned active + stale + retracted scenario for the UI / acceptance (§23.27).

    Demonstrates the §23.27 criterion end-to-end: a retracted primary source is
    still listed but carries a warning and drags the verifier confidence down,
    while freshness is shown for every citation.
    """
    citations = [
        {
            "doc_id": "desal-review-2022",
            "source_status": "active",
            "age_days": 400,
            "peer_reviewed": True,
            "citation_count": 42,
            "primary": True,
        },
        {
            "doc_id": "legacy-flotation-2009",
            "source_status": "active",
            "age_days": 5200,
            "peer_reviewed": True,
            "citation_count": 8,
            "primary": False,
        },
        {
            "doc_id": "retracted-leach-2021",
            "source_status": "retracted",
            "age_days": 900,
            "peer_reviewed": True,
            "citation_count": 15,
            "primary": True,
        },
        {
            "doc_id": "vendor-whitepaper",
            "source_status": "deprecated",
            "age_days": 220,
            "peer_reviewed": False,
            "citation_count": 0,
            "primary": False,
        },
    ]
    report = assess_answer(citations, base_confidence=0.86)
    return report.as_dict()

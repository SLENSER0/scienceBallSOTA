"""Provenance context for agent citations — owner/lab/version/freshness (§10.10).

The chat/answer surface already renders the *geo / year / date-of-actualization*
triple on every citation (see ``Citation.as_of`` + AskView). §10.10 completes that
triple into a **full provenance block** on each citation: who *owns* the source, in
which *lab* it lives, its catalog *version*, its *freshness* verdict, plus the
*extractor / model* that produced the facts and the curation *review_status*.

All the scoring/enrichment logic already ships as pure, tested modules —
:mod:`kg_common.citation_provenance` (:func:`enrich_all`) and
:mod:`kg_common.source_freshness` (:func:`classify`). This router does only the
HTTP + graph-lookup glue: for each cited ``doc_id`` it reads the source node from
the live graph store (Neo4j server profile), derives the provenance fields, turns
``source_date`` / ``created_at`` into a freshness verdict at the caller's
``as_of`` clock, and returns citations enriched with a nested ``provenance`` block.

Endpoints:

* ``POST /api/v1/citation-provenance/enrich`` — enrich a list of citations with
  provenance resolved from the graph; returns a coverage summary and the list of
  doc_ids that had no resolvable source node.
* ``GET  /api/v1/citation-provenance/source/{doc_id}`` — the provenance card for
  a single source.
* ``GET  /api/v1/citation-provenance/demo`` — a canned full-provenance scenario so
  the UI (and the §10.10 acceptance demo) has owner/lab/version/freshness data
  even before the catalog is populated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api_gateway.auth import current_role
from api_gateway.deps import get_store
from kg_common.citation_provenance import enrich_all, missing_provenance
from kg_common.source_freshness import Freshness, classify

router = APIRouter(prefix="/api/v1/citation-provenance", tags=["citation-provenance"])


# --------------------------------------------------------------------------- #
# Request models                                                              #
# --------------------------------------------------------------------------- #


class CitationIn(BaseModel):
    """One citation to enrich — identified by its source doc/evidence ids."""

    doc_id: str = ""
    source_id: str | None = None
    evidence_id: str | None = None
    marker: str | None = None  # e.g. "[1]" — echoed back untouched


class EnrichRequest(BaseModel):
    citations: list[CitationIn] = Field(default_factory=list)
    # ISO-8601 «as-of» clock for the freshness verdict; defaults to now (UTC).
    as_of: str | None = None
    fresh_days: int = 30
    stale_days: int = 180


# --------------------------------------------------------------------------- #
# Field resolution — read provenance from the live graph node                  #
# --------------------------------------------------------------------------- #

#: Candidate node keys per provenance field — first non-empty wins («каталог»).
_FIELD_KEYS: dict[str, tuple[str, ...]] = {
    "owner": ("owner", "author", "authors", "source_owner", "organization"),
    "lab": ("lab", "laboratory", "affiliation", "institution"),
    "version": ("version", "data_version", "schema_version"),
    "extractor": ("extractor", "extractor_name", "extractor_run_id"),
    "model": ("model", "extractor_model", "llm_model", "model_version"),
    "review_status": ("review_status",),
}

#: Node keys that carry the last-ingest / actualization timestamp — freshness.
_DATE_KEYS: tuple[str, ...] = ("source_date", "ingested_at", "created_at", "date")


def _first_str(node: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """First present, non-empty value among ``keys``, stringified — or None."""
    for key in keys:
        raw = node.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return None


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (tolerating a trailing ``Z``) — or None."""
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        # Bare date «2024» or «2024-05» — best-effort year/day only.
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _resolve_node(cit: CitationIn) -> dict[str, Any] | None:
    """Look up the source node behind a citation — doc_id, then source/evidence.

    Tries the candidate ids in order and returns the first node the store knows.
    Returns ``None`` when none resolve (the citation then carries only its
    ``doc_id`` in provenance).
    """
    store = get_store()
    for node_id in (cit.doc_id, cit.source_id, cit.evidence_id):
        if not node_id:
            continue
        try:
            node = store.get_node(node_id)
        except Exception:  # pragma: no cover - store defensiveness
            node = None
        if node:
            return node
    return None


def _freshness_for(
    node: dict[str, Any], source_id: str, req: EnrichRequest, as_of: datetime
) -> Freshness:
    """Classify a node's freshness from its actualization timestamp (§10.7)."""
    last_ingest = None
    for key in _DATE_KEYS:
        last_ingest = _parse_dt(node.get(key) if isinstance(node.get(key), str) else None)
        if last_ingest is not None:
            break
    return classify(
        source_id=source_id,
        last_ingest_at=last_ingest,
        as_of=as_of,
        fresh_days=req.fresh_days,
        stale_days=req.stale_days,
    )


def _source_meta(cit: CitationIn, req: EnrichRequest, as_of: datetime) -> dict[str, Any] | None:
    """Provenance metadata for one citation, or ``None`` when unresolvable.

    Reads the live graph node behind the citation and maps its fields onto the
    provenance schema (owner/lab/version/extractor/model/review_status) plus a
    freshness verdict. The ``freshness`` field is the level string; a richer
    ``freshness_detail`` block (level/age_days/last_ingest_at) is attached by the
    caller after enrichment.
    """
    node = _resolve_node(cit)
    if node is None:
        return None
    source_id = cit.doc_id or cit.source_id or str(node.get("id", ""))
    meta: dict[str, Any] = {}
    for field, keys in _FIELD_KEYS.items():
        value = _first_str(node, keys)
        if value is not None:
            meta[field] = value
    fresh = _freshness_for(node, source_id, req, as_of)
    meta["freshness"] = fresh.level
    meta["_freshness_detail"] = fresh.as_dict()
    return meta


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


def _now(as_of: str | None) -> datetime:
    parsed = _parse_dt(as_of)
    return parsed if parsed is not None else datetime.now(UTC)


@router.post("/enrich")
def enrich(req: EnrichRequest, _role: str = Depends(current_role)) -> dict[str, Any]:
    """Enrich citations with owner/lab/version/freshness provenance (§10.10).

    For every citation the source node is resolved from the live graph and its
    provenance fields are merged into a nested ``provenance`` block via the pure
    :func:`kg_common.citation_provenance.enrich_all`. Unresolved citations still
    appear (their provenance carries only the ``doc_id``) and are listed under
    ``missing_provenance``.
    """
    as_of = _now(req.as_of)

    raw_citations: list[dict[str, Any]] = []
    source_index: dict[str, dict[str, Any]] = {}
    detail_index: dict[str, dict[str, Any]] = {}
    for cit in req.citations:
        doc_id = cit.doc_id or cit.source_id or cit.evidence_id or ""
        raw = {"doc_id": doc_id}
        if cit.marker is not None:
            raw["marker"] = cit.marker
        raw_citations.append(raw)
        meta = _source_meta(cit, req, as_of)
        if meta is not None:
            detail = meta.pop("_freshness_detail", None)
            source_index[doc_id] = meta
            if detail is not None:
                detail_index[doc_id] = detail

    enriched = enrich_all(raw_citations, source_index)
    # Fold the richer freshness detail back into each provenance block.
    for cit_out in enriched:
        prov = cit_out.get("provenance")
        doc_id = str(cit_out.get("doc_id", ""))
        if isinstance(prov, dict) and doc_id in detail_index:
            prov["freshness_detail"] = detail_index[doc_id]

    missing = missing_provenance(raw_citations, source_index)
    fields = ("owner", "lab", "version", "freshness", "extractor", "model", "review_status")
    coverage = {
        field: sum(1 for m in source_index.values() if m.get(field)) for field in fields
    }
    fresh_levels = [m.get("freshness") for m in source_index.values()]
    summary = {
        "total": len(raw_citations),
        "resolved": len(source_index),
        "missing": len(missing),
        "coverage": coverage,
        "fresh": fresh_levels.count("fresh"),
        "aging": fresh_levels.count("aging"),
        "stale": fresh_levels.count("stale"),
        "unknown": fresh_levels.count("unknown"),
    }
    return {
        "as_of": as_of.isoformat(),
        "citations": enriched,
        "missing_provenance": missing,
        "summary": summary,
    }


@router.get("/source/{doc_id:path}")
def source_card(
    doc_id: str,
    as_of: str | None = None,
    _role: str = Depends(current_role),
) -> dict[str, Any]:
    """Full provenance card for a single source (§10.10)."""
    clock = _now(as_of)
    req = EnrichRequest()
    meta = _source_meta(CitationIn(doc_id=doc_id), req, clock)
    if meta is None:
        return {
            "doc_id": doc_id,
            "resolved": False,
            "provenance": {"doc_id": doc_id},
        }
    detail = meta.pop("_freshness_detail", None)
    provenance = {"doc_id": doc_id, **meta}
    if detail is not None:
        provenance["freshness_detail"] = detail
    return {"doc_id": doc_id, "resolved": True, "provenance": provenance}


@router.get("/demo")
def demo(_role: str = Depends(current_role)) -> dict[str, Any]:
    """Canned full-provenance scenario for the UI / §10.10 acceptance.

    Shows every provenance field populated across a fresh, an aging and a stale
    source so the citation-provenance panel renders owner/lab/version/freshness
    even before the live catalog is backfilled.
    """
    as_of = datetime(2026, 7, 4, tzinfo=UTC)
    citations = [
        {
            "doc_id": "paper-heap-leach-2026",
            "marker": "[1]",
            "provenance": {
                "doc_id": "paper-heap-leach-2026",
                "owner": "Гидрометаллургическая лаборатория",
                "lab": "hydrometallurgy lab",
                "version": "3",
                "freshness": "fresh",
                "extractor": "gliner-mining-v2",
                "model": "Qwen3-32B",
                "review_status": "accepted",
                "freshness_detail": {
                    "source_id": "paper-heap-leach-2026",
                    "last_ingest_at": "2026-06-20T00:00:00+00:00",
                    "age_days": 14,
                    "level": "fresh",
                },
            },
        },
        {
            "doc_id": "paper-flotation-2025",
            "marker": "[2]",
            "provenance": {
                "doc_id": "paper-flotation-2025",
                "owner": "ИГД УрО РАН",
                "lab": "beneficiation lab",
                "version": "2",
                "freshness": "aging",
                "extractor": "llm-ie",
                "model": "GLM-5.2",
                "review_status": "pending",
                "freshness_detail": {
                    "source_id": "paper-flotation-2025",
                    "last_ingest_at": "2026-02-01T00:00:00+00:00",
                    "age_days": 153,
                    "level": "aging",
                },
            },
        },
        {
            "doc_id": "legacy-smelting-2009",
            "marker": "[3]",
            "provenance": {
                "doc_id": "legacy-smelting-2009",
                "owner": "Norilsk Nickel R&D",
                "lab": "pyrometallurgy lab",
                "version": "1",
                "freshness": "stale",
                "extractor": "gliner-mining-v1",
                "model": "Qwen2.5-14B",
                "review_status": "accepted",
                "freshness_detail": {
                    "source_id": "legacy-smelting-2009",
                    "last_ingest_at": "2024-01-10T00:00:00+00:00",
                    "age_days": 906,
                    "level": "stale",
                },
            },
        },
    ]
    summary = {
        "total": 3,
        "resolved": 3,
        "missing": 0,
        "coverage": {
            "owner": 3,
            "lab": 3,
            "version": 3,
            "freshness": 3,
            "extractor": 3,
            "model": 3,
            "review_status": 3,
        },
        "fresh": 1,
        "aging": 1,
        "stale": 1,
        "unknown": 0,
    }
    return {
        "as_of": as_of.isoformat(),
        "citations": citations,
        "missing_provenance": [],
        "summary": summary,
    }

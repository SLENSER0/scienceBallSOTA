"""Prose LLM-claim extraction surface (§25.6).

Exposes the previously-inactive prose extractor (``llm_claims_from_text``) over
HTTP so the value of enabling it is visible and demonstrable on the live graph,
**without** touching the ingestion graph or writing anything to the store:

* ``GET  /api/v1/prose-claims/status`` — the feature-flag state, LLM availability,
  the prose recall priors (LLM 0.55 vs offline 0.15 → ``p_missed``) and the live
  extraction blind-spot report (materials MENTIONED in prose yet never measured —
  exactly what prose extraction would recover). Reuses
  :func:`kg_retrievers.blindspot_report.build_blindspot_report`.
* ``GET  /api/v1/prose-claims/chunks`` — a sample of prose ``Chunk`` nodes from the
  graph the UI can trial extraction on.
* ``POST /api/v1/prose-claims/extract`` — run the governed extractor on a chunk (by
  id, text fetched from the graph) or on ad-hoc ``text``. Returns governed
  *proposals* (``status="proposed"``) with the reused chunk evidence span, plus the
  coverage record. An ``enabled`` override lets the client demonstrate **both**
  branches (offline blind-spot vs LLM proposals) irrespective of the config flag —
  it never merges anything, so the demo is side-effect free.

All extraction logic lives in :mod:`kg_extractors.prose_claims`; this router only
does HTTP, a read-only chunk lookup and the flag/availability probe.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api_gateway.deps import get_store
from kg_common import get_settings
from kg_extractors.prose_claims import FLAG_ATTR, PROSE_MODALITY, llm_claims_from_text

router = APIRouter(prefix="/api/v1/prose-claims", tags=["prose-claims"])


# --------------------------------------------------------------------------- #
# Availability probe                                                          #
# --------------------------------------------------------------------------- #
def _flag_enabled() -> bool:
    try:
        return bool(getattr(get_settings(), FLAG_ATTR, False))
    except Exception:
        return False


def _llm_available() -> bool:
    try:
        return bool(get_settings().llm_api_key.get_secret_value())
    except Exception:
        return False


def _prose_priors() -> dict[str, Any]:
    """Static prose recall priors (§25.10) as ``recall`` + derived ``p_missed``."""
    from kg_retrievers.modality_recall_prior import recall_for_context

    llm = recall_for_context(PROSE_MODALITY, llm_enabled=True)
    offline = recall_for_context(PROSE_MODALITY, llm_enabled=False)
    return {
        "llm": {"recall": llm.recall, "p_missed": round(1.0 - llm.recall, 4)},
        "offline": {"recall": offline.recall, "p_missed": round(1.0 - offline.recall, 4)},
        "calibrated": False,
    }


# --------------------------------------------------------------------------- #
# GET /status                                                                 #
# --------------------------------------------------------------------------- #
@router.get("/status")
def status(
    blindspot_top: int = Query(default=15, ge=0, le=100),
    with_blindspot: bool = Query(default=True),
) -> dict:
    """Feature state + prose priors + live extraction blind spots (§25.6)."""
    store = get_store()
    flag = _flag_enabled()
    llm = _llm_available()

    blindspot: dict | None = None
    if with_blindspot:
        try:
            from kg_retrievers.blindspot_report import build_blindspot_report

            blindspot = build_blindspot_report(store, top=blindspot_top).as_dict()
        except Exception as exc:  # graph may be tiny / schema mismatch — non-fatal.
            blindspot = {"error": f"{type(exc).__name__}: {exc}"}

    prose_chunks = _count_prose_chunks(store)
    return {
        "flag_enabled": flag,
        "llm_available": llm,
        "active": flag and llm,
        "flag_attr": FLAG_ATTR,
        "priors": _prose_priors(),
        "prose_chunks": prose_chunks,
        "blindspot": blindspot,
        "note": (
            "Prose extraction emits governed proposals (proposal → validate → review); "
            "nothing is merged from this surface."
        ),
    }


def _count_prose_chunks(store) -> int:  # type: ignore[no-untyped-def]
    try:
        rows = store.rows(
            "MATCH (c:Node) WHERE c.label='Chunk' "
            "AND coalesce(c.chunk_type,'prose')='prose' RETURN count(c)"
        )
        return int(rows[0][0]) if rows and rows[0] else 0
    except Exception:
        return 0


# --------------------------------------------------------------------------- #
# GET /chunks — sample prose chunks to trial on                               #
# --------------------------------------------------------------------------- #
@router.get("/chunks")
def chunks(limit: int = Query(default=20, ge=1, le=200)) -> dict:
    """A sample of prose ``Chunk`` nodes (id, doc, text) for the trial panel."""
    store = get_store()
    try:
        rows = store.rows(
            "MATCH (d:Node)-[r:Rel]->(c:Node) "
            "WHERE d.label='Document' AND r.type='HAS_CHUNK' AND c.label='Chunk' "
            "AND coalesce(c.chunk_type,'prose')='prose' "
            "AND coalesce(c.text, c.content, '') <> '' "
            "RETURN c.id, d.id, coalesce(c.text, c.content, ''), "
            "c.page, c.char_start, c.char_end "
            f"LIMIT {int(limit)}",
        )
    except Exception as exc:
        return {"chunks": [], "error": f"{type(exc).__name__}: {exc}"}

    out = []
    for cid, did, text, page, cs, ce in rows:
        out.append(
            {
                "chunk_id": cid,
                "doc_id": did,
                "text": text,
                "page": _int_or_none(page),
                "char_start": _int_or_none(cs),
                "char_end": _int_or_none(ce),
            }
        )
    return {"chunks": out}


def _int_or_none(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# POST /extract — run the governed extractor                                  #
# --------------------------------------------------------------------------- #
class ExtractRequest(BaseModel):
    chunk_id: str | None = None
    text: str | None = None
    doc_id: str | None = None
    # Override the config flag for demonstration (None → use config). The extractor
    # never merges, so forcing the LLM branch here is safe.
    enabled: bool | None = None


@router.post("/extract")
def extract(req: ExtractRequest) -> dict:
    """Run ``llm_claims_from_text`` on a chunk or ad-hoc text (§25.6, governed)."""
    store = get_store()
    text = req.text
    doc_id = req.doc_id or ""
    chunk_id = req.chunk_id or "adhoc:0"
    page = char_start = char_end = None

    if req.chunk_id:
        fetched = _fetch_chunk(store, req.chunk_id)
        if fetched is None:
            return {"error": f"chunk not found: {req.chunk_id}"}
        text = fetched["text"] if text is None else text
        doc_id = doc_id or fetched["doc_id"]
        page = fetched["page"]
        char_start = fetched["char_start"]
        char_end = fetched["char_end"]

    if not text:
        return {"error": "no text (provide chunk_id of a prose chunk or raw text)"}

    extraction = llm_claims_from_text(
        text,
        chunk_id=chunk_id,
        doc_id=doc_id,
        page=page,
        char_start=char_start,
        char_end=char_end,
        enabled=req.enabled,
    )
    result = extraction.as_dict()
    result["input"] = {"chunk_id": chunk_id, "doc_id": doc_id, "chars": len(text)}
    return result


def _fetch_chunk(store, chunk_id: str) -> dict | None:  # type: ignore[no-untyped-def]
    try:
        rows = store.rows(
            "MATCH (c:Node {id:$cid}) WHERE c.label='Chunk' "
            "OPTIONAL MATCH (d:Node)-[r:Rel]->(c) "
            "WHERE d.label='Document' AND r.type='HAS_CHUNK' "
            "RETURN coalesce(c.text, c.content, ''), d.id, "
            "c.page, c.char_start, c.char_end LIMIT 1",
            {"cid": chunk_id},
        )
    except Exception:
        return None
    if not rows or not rows[0]:
        return None
    text, did, page, cs, ce = rows[0]
    return {
        "text": text or "",
        "doc_id": did or "",
        "page": _int_or_none(page),
        "char_start": _int_or_none(cs),
        "char_end": _int_or_none(ce),
    }

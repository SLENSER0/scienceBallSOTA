"""Full schema-guided ExperimentExtract surface (§6.9).

Exposes :func:`kg_extractors.experiment_extractor.extract_experiment` over HTTP so
the §6.9 value — a complete ``ExperimentExtract`` with an explicit Claim-vs-Finding
split and transparent retry/repair of invalid LLM JSON — is demonstrable on the
live server graph (Neo4j :8000) **without writing anything** to the store:

* ``GET  /api/v1/experiment-extract/status`` — LLM availability + configured OSS
  extraction model + a count of prose chunks to trial on.
* ``GET  /api/v1/experiment-extract/chunks`` — a sample of prose ``Chunk`` nodes
  (id, doc, text) the UI can run extraction on.
* ``POST /api/v1/experiment-extract/extract`` — run the extractor on a chunk (by id,
  text fetched read-only from the graph) or on ad-hoc ``text``. Returns the full
  ``FullExperimentExtract`` plus the repair trace (attempts / repaired / dropped).

All extraction logic — the JSON-mode call, the Claim-vs-Finding derivation and the
bounded retry/repair + controlled-drop — lives in the extractor module; this router
only does HTTP and a read-only chunk lookup.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api_gateway.deps import get_store
from kg_common import get_settings

router = APIRouter(prefix="/api/v1/experiment-extract", tags=["experiment-extract"])


# --------------------------------------------------------------------------- #
# Availability                                                                 #
# --------------------------------------------------------------------------- #
def _llm_available() -> bool:
    try:
        return bool(get_settings().llm_api_key.get_secret_value())
    except Exception:
        return False


def _extract_model() -> str:
    try:
        return str(get_settings().llm_model_extract)
    except Exception:
        return "unknown"


def _int_or_none(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


@router.get("/status")
def status() -> dict:
    """LLM availability + configured OSS extraction model + trial chunk count."""
    store = get_store()
    prose = 0
    try:
        rows = store.rows(
            "MATCH (c:Node) WHERE c.label='Chunk' "
            "AND coalesce(c.chunk_type,'prose')='prose' RETURN count(c)"
        )
        prose = int(rows[0][0]) if rows and rows[0] else 0
    except Exception:
        prose = 0
    return {
        "llm_available": _llm_available(),
        "model": _extract_model(),
        "prose_chunks": prose,
        "note": (
            "Full ExperimentExtract (§6.9): Claim-vs-Finding split + bounded "
            "retry/repair of invalid JSON. Read-only — nothing is written to the graph."
        ),
    }


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
            "RETURN c.id, d.id, coalesce(c.text, c.content, ''), c.page "
            f"LIMIT {int(limit)}",
        )
    except Exception as exc:
        return {"chunks": [], "error": f"{type(exc).__name__}: {exc}"}
    out = []
    for cid, did, text, page in rows:
        out.append(
            {
                "chunk_id": cid,
                "doc_id": did,
                "text": text,
                "page": _int_or_none(page),
            }
        )
    return {"chunks": out}


class ExtractRequest(BaseModel):
    chunk_id: str | None = None
    text: str | None = None
    max_repairs: int = 2


@router.post("/extract")
def extract(req: ExtractRequest) -> dict:
    """Run the full ExperimentExtract on a chunk or ad-hoc text (§6.9, read-only)."""
    from kg_extractors.experiment_extractor import extract_experiment

    store = get_store()
    text = req.text
    chunk_id = req.chunk_id or "adhoc:0"
    doc_id = ""

    if req.chunk_id:
        fetched = _fetch_chunk(store, req.chunk_id)
        if fetched is None:
            return {"error": f"chunk not found: {req.chunk_id}"}
        text = fetched["text"] if text is None else text
        doc_id = fetched["doc_id"]

    if not text or not text.strip():
        return {"error": "no text (provide chunk_id of a prose chunk or raw text)"}

    if not _llm_available():
        return {
            "error": "LLM unavailable (no OPENROUTER_API_KEY configured).",
            "llm_available": False,
            "input": {"chunk_id": chunk_id, "doc_id": doc_id, "chars": len(text)},
        }

    try:
        result = extract_experiment(text, max_repairs=max(0, min(int(req.max_repairs), 4)))
    except Exception as exc:  # extractor is drop-safe, but never 500 the demo.
        return {"error": f"{type(exc).__name__}: {exc}"}

    payload = result.as_dict()
    payload["input"] = {"chunk_id": chunk_id, "doc_id": doc_id, "chars": len(text)}
    payload["llm_available"] = True
    return payload


def _fetch_chunk(store, chunk_id: str) -> dict | None:  # type: ignore[no-untyped-def]
    try:
        rows = store.rows(
            "MATCH (c:Node {id:$cid}) WHERE c.label='Chunk' "
            "OPTIONAL MATCH (d:Node)-[r:Rel]->(c) "
            "WHERE d.label='Document' AND r.type='HAS_CHUNK' "
            "RETURN coalesce(c.text, c.content, ''), d.id LIMIT 1",
            {"cid": chunk_id},
        )
    except Exception:
        return None
    if not rows or not rows[0]:
        return None
    text, did = rows[0]
    return {"text": text or "", "doc_id": did or ""}

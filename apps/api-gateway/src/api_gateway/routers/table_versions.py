"""§5.8 Parsed-table versions + manual correction + fallback-parser status.

Two related §5.8 surfaces, kept off the ``/documents`` catch-all prefix so they
never collide with the ``documents`` router's greedy ``/{doc_id:path}`` route:

**Manual table correction as a new artifact version** (mitigation §18). A curator
opens a parsed table, retypes the grid, and submits it — the correction is stored
as a *new version* (``corrected=true`` / ``parser_used="manual"``) that never
overwrites the parser's original (v0). Backed by
:mod:`api_gateway.table_versions_store`.

* ``GET  /api/v1/parsed-tables/{doc_id}``                      — tables in a doc + lineage summary.
* ``GET  /api/v1/parsed-tables/{doc_id}/{index}``             — current (effective) grid.
* ``GET  /api/v1/parsed-tables/{doc_id}/{index}/versions``    — full v0→vN lineage.
* ``POST /api/v1/parsed-tables/{doc_id}/{index}/correct``     — append a corrected version.

**Fallback-parser status** — which of docling / marker / unstructured / default
are ready, and the per-format priority order that drives the fallback chain
(:mod:`ingestion_service.fallback_parsers`).

* ``GET  /api/v1/parsers/fallback-status`` — readiness + priority table.

Writes are RBAC-gated to the curator-and-up roles and audited (§24.14); the
correction event is echoed to the governance/curation log so §16 review can pick
it up.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api_gateway import audit
from api_gateway.auth import current_role, current_user
from api_gateway.table_versions_store import (
    DocumentNotFound,
    InvalidRows,
    TableNotFound,
    append_correction,
    base_table_count,
    current_table,
    list_versions,
)

router = APIRouter(prefix="/api/v1", tags=["parsed-tables", "parsers"])

# Same write-capable roles as manual table upload / curation (§16/§19).
_CAN_CORRECT = {"admin", "curator", "researcher", "analyst", "project_manager"}


def _require_correct(role: str) -> None:
    if role not in _CAN_CORRECT:
        raise HTTPException(status_code=403, detail="role may not correct parsed tables")


# -- fallback-parser status ----------------------------------------------------
@router.get("/parsers/fallback-status")
def fallback_status() -> dict:
    """Which §5.8 parsers are ready + the per-format fallback priority order.

    ``parsers`` reports docling (service reachable?), marker/unstructured (optional
    dependency importable?) and the always-ready builtin default. ``priority``
    shows the ordered chain each format walks (docling→…→default), so the UI can
    explain *why* a document fell back.
    """
    from ingestion_service.fallback_parsers import parser_readiness
    from ingestion_service.parser_priority import DEFAULT_TABLE

    readiness = parser_readiness()
    return {
        "parsers": readiness,
        "priority": DEFAULT_TABLE.as_dict(),
        "primary": "docling",
        "primaryAvailable": bool(readiness.get("docling", {}).get("available")),
    }


# -- table lineage reads -------------------------------------------------------
@router.get("/parsed-tables/{doc_id}")
def document_tables(doc_id: str) -> dict:
    """List the parsed tables of a document with a per-table lineage summary."""
    try:
        n = base_table_count(doc_id)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc
    tables = []
    for i in range(n):
        lineage = list_versions(doc_id, i)
        cur = lineage.current
        tables.append(
            {
                "tableIndex": i,
                "page": cur.page,
                "nRows": len(cur.rows),
                "nCols": max((len(r) for r in cur.rows), default=0),
                "corrected": lineage.as_dict()["corrected"],
                "versionCount": len(lineage.versions),
                "currentVersion": cur.version,
                "parserUsed": cur.parser_used,
            }
        )
    return {"docId": doc_id, "tableCount": n, "tables": tables}


@router.get("/parsed-tables/{doc_id}/{table_index}")
def table_current(doc_id: str, table_index: int) -> dict:
    """The effective (latest) version of one parsed table."""
    try:
        return current_table(doc_id, table_index).as_dict()
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc
    except TableNotFound as exc:
        raise HTTPException(status_code=404, detail="table not found") from exc


@router.get("/parsed-tables/{doc_id}/{table_index}/versions")
def table_versions(doc_id: str, table_index: int) -> dict:
    """Full lineage of a parsed table: original (v0) + every correction."""
    try:
        return list_versions(doc_id, table_index).as_dict()
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc
    except TableNotFound as exc:
        raise HTTPException(status_code=404, detail="table not found") from exc


# -- manual correction (new version) -------------------------------------------
class CorrectionBody(BaseModel):
    """A hand-corrected table grid (§5.8 manual table upload)."""

    rows: list[list[str]] = Field(default_factory=list)
    reason: str = ""


@router.post("/parsed-tables/{doc_id}/{table_index}/correct")
def correct_table(
    doc_id: str,
    table_index: int,
    body: CorrectionBody,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """Store a manual table correction as a **new version** (original preserved).

    The new version is tagged ``corrected=true`` / ``parser_used="manual"`` and
    appended after the highest existing version; v0 (the parser output) is never
    touched. The event is audited and echoed to governance/curation (§16/§24.14).
    Returns the new version plus the refreshed lineage so the UI can re-render.
    """
    _require_correct(role)
    try:
        version = append_correction(
            doc_id, table_index, body.rows, reason=body.reason, author=user
        )
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc
    except TableNotFound as exc:
        raise HTTPException(status_code=404, detail="table not found") from exc
    except InvalidRows as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    detail = {
        "doc_id": doc_id,
        "table_index": table_index,
        "version": version.version,
        "parser_used": version.parser_used,
        "corrected": version.corrected,
        "reason": version.reason,
    }
    # §24.14 audit + §16 governance/curation echo (same append-only log).
    audit.record("correct_parsed_table", user=user, role=role, detail=detail)
    audit.record("curation.table_corrected", user=user, role=role, detail=detail)

    return {
        "created": version.as_dict(),
        "lineage": list_versions(doc_id, table_index).as_dict(),
    }

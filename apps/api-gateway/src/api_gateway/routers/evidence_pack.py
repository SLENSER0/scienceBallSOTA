"""Reproducible Evidence Pack export + deterministic replay (§23.29).

Turns one agent answer into a downloadable, verifiable bundle and lets a
researcher *replay* it on the same data snapshot:

* ``POST /api/v1/answers/evidence-pack`` — run the query, build the pack and
  return it in the requested ``format`` (``json`` | ``html`` | ``pdf`` | ``zip``).
  The response carries an ``answer_id`` (header ``X-Answer-Id``) that keys the
  replay endpoint.
* ``GET  /api/v1/answers/{answer_id}/evidence-pack`` — re-download a pack for a
  previously exported answer (re-runs on the same params).
* ``POST /api/v1/answers/{answer_id}/replay`` — re-run on the same snapshot and
  report whether the answer reproduced (identical content fingerprint) or, if
  not, which fields diverged and why (§23.29 acceptance).

The heavy lifting is in :mod:`api_gateway.evidence_pack`, which reuses the
already-shipped manifest / provenance-completeness / run-fingerprint engines.
This router only wires HTTP, auth and audit around it.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from api_gateway import audit
from api_gateway import evidence_pack as ep
from api_gateway.auth import current_role, current_user
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/answers", tags=["evidence-pack"])

_FORMATS = {"json", "html", "pdf", "zip"}


class EvidencePackRequest(BaseModel):
    query: str
    role: str = "researcher"
    use_llm: bool = True
    geography: str | None = None  # russia | cis | foreign | global | all | None


def _normalized_query(answer: Any, fallback: str) -> str:
    """Best-effort normalized query from the answer's parsed_query — нормализованный запрос."""
    parsed = getattr(answer, "parsed_query", None) or {}
    for key in ("normalized", "normalized_question", "raw", "query"):
        val = parsed.get(key)
        if val:
            return str(val)
    return fallback


def _run(query: str, role: str, use_llm: bool, geography: str | None) -> Any:
    from agent_service.agent import answer_query

    geo = geography if geography and geography != "all" else None
    return answer_query(query, get_store(), role=role, use_llm=use_llm, geography=geo)


def _build(
    query: str, role: str, use_llm: bool, geography: str | None
) -> tuple[Any, ep.PackContext]:
    """Run the query and build a remembered pack context — прогон + контекст пакета."""
    answer = _run(query, role, use_llm, geography)
    store = get_store()
    provenance = ep.build_provenance(answer, store)
    fingerprint = ep.answer_fingerprint(answer)
    snapshot_id = ep.build_snapshot_id(store)
    answer_id = ep.deterministic_answer_id(query, role, geography, use_llm)
    ctx = ep.PackContext(
        answer_id=answer_id,
        query=query,
        role=role,
        geography=geography,
        use_llm=use_llm,
        fingerprint=fingerprint,
        snapshot_id=snapshot_id,
        provenance=provenance,
        field_fingerprints=ep.field_fingerprints(answer),
    )
    ep.remember_request(ctx)
    return answer, ctx


def _respond(answer: Any, ctx: ep.PackContext, fmt: str) -> Response:
    """Serialise the pack in the requested format — сериализация пакета."""
    normalized = _normalized_query(answer, ctx.query)
    files, manifest = ep.assemble_pack(
        ctx.query,
        normalized,
        answer,
        ctx.provenance,
        fingerprint=ctx.fingerprint,
        answer_id=ctx.answer_id,
    )
    headers = {"X-Answer-Id": ctx.answer_id, "X-Pack-Root-Sha256": manifest.root_sha256}
    stem = ctx.answer_id

    if fmt == "html":
        return HTMLResponse(files["report.html"].decode("utf-8"), headers=headers)
    if fmt == "pdf":
        pdf = ep.render_pdf(ctx.query, answer, ctx.provenance, manifest)
        headers["Content-Disposition"] = f'attachment; filename="{stem}.pdf"'
        return Response(pdf, media_type="application/pdf", headers=headers)
    if fmt == "zip":
        blob = ep.pack_zip(files)
        headers["Content-Disposition"] = f'attachment; filename="{stem}.zip"'
        return Response(blob, media_type="application/zip", headers=headers)
    # json: manifest + provenance + answer + verification metadata
    body = {
        "answer_id": ctx.answer_id,
        "manifest": manifest.as_dict(),
        "answer": answer.model_dump(by_alias=True),
        "provenance": ctx.provenance,
        "answer_fingerprint": ctx.fingerprint,
        "snapshot_id": ctx.snapshot_id,
        "replay_url": f"/api/v1/answers/{ctx.answer_id}/replay",
    }
    return Response(
        content=json.dumps(body, ensure_ascii=False, default=str),
        media_type="application/json",
        headers=headers,
    )


@router.post("/evidence-pack")
def export_evidence_pack(
    req: EvidencePackRequest,
    format: str = Query("zip"),
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> Response:
    """Export an answer as a reproducible evidence pack — экспорт пакета (§23.29)."""
    fmt = format.lower()
    if fmt not in _FORMATS:
        raise HTTPException(400, f"format must be one of {sorted(_FORMATS)}")
    answer, ctx = _build(req.query, req.role, req.use_llm, req.geography)
    audit.record(
        "evidence_pack_export",
        user=user,
        role=role,
        detail={"answer_id": ctx.answer_id, "format": fmt, "q": req.query[:120]},
    )
    return _respond(answer, ctx, fmt)


@router.get("/{answer_id}/evidence-pack")
def download_evidence_pack(
    answer_id: str,
    format: str = Query("zip"),
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> Response:
    """Re-download the pack for a known answer_id — повторная выгрузка пакета (§23.29)."""
    fmt = format.lower()
    if fmt not in _FORMATS:
        raise HTTPException(400, f"format must be one of {sorted(_FORMATS)}")
    ctx = ep.recall_request(answer_id)
    if ctx is None:
        raise HTTPException(404, "unknown answer_id — export it first via POST /evidence-pack")
    answer, ctx = _build(ctx.query, ctx.role, ctx.use_llm, ctx.geography)
    audit.record(
        "evidence_pack_download",
        user=user,
        role=role,
        detail={"answer_id": answer_id, "format": fmt},
    )
    return _respond(answer, ctx, fmt)


class ReplayRequest(BaseModel):
    # Fallback params so replay still works after a process restart clears the
    # in-memory registry — параметры на случай перезапуска процесса.
    query: str | None = None
    role: str = "researcher"
    use_llm: bool = True
    geography: str | None = None


@router.post("/{answer_id}/replay")
def replay_answer(
    answer_id: str,
    req: ReplayRequest | None = None,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict[str, Any]:
    """Deterministic replay on the same snapshot — детерминированный replay (§23.29).

    Re-runs the remembered request and reports ``reproduced`` (identical content
    fingerprint) or, on divergence, which fields changed and whether the data
    snapshot moved underneath — satisfying the §23.29 acceptance criterion.
    """
    ctx = ep.recall_request(answer_id)
    if ctx is None:
        if req is None or not req.query:
            raise HTTPException(
                404,
                "unknown answer_id — export it first, or POST the original query in the body",
            )
        # Rebuild the original identity from the supplied params.
        _, ctx = _build(req.query, req.role, req.use_llm, req.geography)

    replay_answer_obj = _run(ctx.query, ctx.role, ctx.use_llm, ctx.geography)
    replay_snapshot = ep.build_snapshot_id(get_store())
    report = ep.compare_replay(ctx, replay_answer_obj, replay_snapshot)
    audit.record(
        "evidence_pack_replay",
        user=user,
        role=role,
        detail={"answer_id": answer_id, "reproduced": report["reproduced"]},
    )
    return report

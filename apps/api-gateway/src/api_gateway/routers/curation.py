"""Curation endpoints (§16 / §24.20) — expert edits, review queue, history."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1", tags=["curation"])


def _svc():  # type: ignore[no-untyped-def]
    from curation_service.curation import CurationService

    return CurationService(get_store())


class EditBody(BaseModel):
    changes: dict[str, Any]
    reason: str = ""


class StatusBody(BaseModel):
    status: str
    reason: str = ""


class AliasBody(BaseModel):
    alias: str


class MergeBody(BaseModel):
    keep_id: str
    drop_id: str
    reason: str = ""


@router.get("/curation/queue")
def review_queue(limit: int = 50) -> dict:
    return {"items": _svc().review_queue(limit)}


@router.get("/entities/{entity_id}/history")
def history(entity_id: str) -> dict:
    return {"history": _svc().history(entity_id)}


@router.post("/entities/{entity_id}/edit")
def edit(entity_id: str, body: EditBody, x_user: str = Header(default="curator")) -> dict:
    try:
        return _svc().edit_node(entity_id, body.changes, actor=x_user, reason=body.reason)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/entities/{entity_id}/status")
def set_status(entity_id: str, body: StatusBody, x_user: str = Header(default="curator")) -> dict:
    try:
        return _svc().set_status(entity_id, body.status, actor=x_user, reason=body.reason)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/entities/{entity_id}/aliases")
def add_alias(entity_id: str, body: AliasBody, x_user: str = Header(default="curator")) -> dict:
    try:
        return _svc().add_alias(entity_id, body.alias, actor=x_user)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/entities/merge")
def merge(body: MergeBody, x_user: str = Header(default="curator")) -> dict:
    try:
        return _svc().merge_entities(body.keep_id, body.drop_id, actor=x_user, reason=body.reason)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


class InferredBody(BaseModel):
    inferred: bool = True
    reason: str = ""


class AnnotateBody(BaseModel):
    note: str


@router.post("/entities/{entity_id}/mark-inferred")
def mark_inferred(
    entity_id: str, body: InferredBody, x_user: str = Header(default="curator")
) -> dict:
    try:
        return _svc().mark_inferred(
            entity_id, inferred=body.inferred, actor=x_user, reason=body.reason
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/entities/{entity_id}/annotate")
def annotate(entity_id: str, body: AnnotateBody, x_user: str = Header(default="curator")) -> dict:
    try:
        return _svc().annotate(entity_id, body.note, actor=x_user)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


class ResolveBody(BaseModel):
    resolution: str
    reason: str = ""


class PracticeBody(BaseModel):
    practice_type: str


@router.post("/contradictions/{contradiction_id}/resolve")
def resolve_contradiction(
    contradiction_id: str, body: ResolveBody, x_user: str = Header(default="curator")
) -> dict:
    try:
        return _svc().resolve_contradiction(
            contradiction_id, resolution=body.resolution, actor=x_user, reason=body.reason
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/entities/{entity_id}/practice-type")
def set_practice_type(
    entity_id: str, body: PracticeBody, x_user: str = Header(default="curator")
) -> dict:
    try:
        return _svc().set_practice_type(entity_id, body.practice_type, actor=x_user)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


class ManualEvidenceBody(BaseModel):
    text: str
    doc_id: str = "manual"
    page: int | None = None


class SplitBody(BaseModel):
    new_name: str
    reason: str = ""


@router.post("/entities/{entity_id}/manual-evidence")
def manual_evidence(
    entity_id: str, body: ManualEvidenceBody, x_user: str = Header(default="curator")
) -> dict:
    try:
        return _svc().add_manual_evidence(
            entity_id, text=body.text, doc_id=body.doc_id, page=body.page, actor=x_user
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/entities/{entity_id}/split")
def split(entity_id: str, body: SplitBody, x_user: str = Header(default="curator")) -> dict:
    try:
        return _svc().split_entity(
            entity_id, new_name=body.new_name, actor=x_user, reason=body.reason
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

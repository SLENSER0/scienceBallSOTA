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

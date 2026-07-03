"""Saved views + user settings endpoints (§14.15)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api_gateway.auth import current_user
from kg_common import get_settings

router = APIRouter(prefix="/api/v1", tags=["views"])

_cache: dict[str, object] = {}


def _views():  # type: ignore[no-untyped-def]
    if "store" not in _cache:
        from kg_common.storage.saved_views import ViewStore

        vs = ViewStore(f"sqlite:///{get_settings().runtime_dir}/views.db")
        vs.migrate()
        _cache["store"] = vs
    return _cache["store"]


class ViewBody(BaseModel):
    name: str
    kind: str = "graph"
    payload: dict[str, Any] = {}


class SettingsBody(BaseModel):
    settings: dict[str, Any]


@router.get("/views")
def list_views(user: str = Depends(current_user)) -> dict:
    return {"views": [v.as_dict() for v in _views().list_views(user)]}


@router.post("/views")
def save_view(body: ViewBody, user: str = Depends(current_user)) -> dict:
    vid = f"view:{uuid.uuid4().hex[:12]}"
    _views().save_view(vid, user, body.name, body.kind, body.payload)
    return _views().get_view(vid).as_dict()


@router.get("/me/settings")
def get_settings_ep(user: str = Depends(current_user)) -> dict:
    return {"user": user, "settings": _views().get_settings(user)}


@router.put("/me/settings")
def put_settings(body: SettingsBody, user: str = Depends(current_user)) -> dict:
    _views().set_settings(user, body.settings)
    return {"user": user, "settings": _views().get_settings(user)}

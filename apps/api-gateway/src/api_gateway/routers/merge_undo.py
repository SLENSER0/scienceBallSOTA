"""Undo-merge endpoints (§8.9) — reversible merges + one-click rollback.

Отдаёт список слияний как обратимые записи (снимок ``before`` в
``CurationEvent{action:merge}`` = обратная ссылка ``merged_from``) и выполняет
откат по ``event_id`` через :class:`~api_gateway.merge_undo.MergeUndoService`.
Работает под живым server-профилем (Neo4j :8000) поверх общего graph-store.

Lists merges as reversible records and rolls a merge back by ``event_id``.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api_gateway.deps import get_store
from api_gateway.merge_undo import MergeUndoService

router = APIRouter(prefix="/api/v1", tags=["curation"])


def _svc() -> MergeUndoService:
    return MergeUndoService(get_store())


class UndoBody(BaseModel):
    reason: str = ""


@router.get("/curation/merges")
def list_merges(limit: int = 50) -> dict:
    """Recent merge events as reversible records (newest first, §8.9)."""
    items = _svc().list_merges(limit)
    return {"count": len(items), "items": items}


@router.post("/curation/merges/{event_id}/undo")
def undo_merge(
    event_id: str, body: UndoBody | None = None, x_user: str = Header(default="curator")
) -> dict:
    """Reverse a merge: restore the absorbed entity, log a compensating split (§8.9)."""
    reason = body.reason if body else ""
    try:
        return _svc().undo_merge(event_id, actor=x_user, reason=reason)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

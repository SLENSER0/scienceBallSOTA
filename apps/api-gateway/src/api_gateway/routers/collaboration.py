"""Collaboration: comments / mentions / shared investigations / notification center (§23.32).

RU: Превращает read-only KG-обозреватель в командный инструмент. Даёт комментарии
к узлам графа (Entity/Experiment/Evidence/Gap/Answer), @mentions, общие
«investigation»-воркспейсы (сохранённая подборка entities+filters+view+notes+
answer history), центр уведомлений (mentioned / assigned_review / evidence_corrected /
gap_closed) и activity feed по проекту/лаборатории. Комментарии НЕ считаются
factual evidence без ручного promoted-статуса (§10.8).

EN: All persistence + notification fan-out lives in the pure, reusable
:class:`kg_common.storage.collaboration.CollaborationStore` (same SQLAlchemy design
as saved-views §14.15); this router is a thin HTTP surface over it. Every write is
attributed to the caller resolved from the auth token (``current_user``), so two
users can jointly work a contradiction/gap: leave comments, @mention each other,
assign an action, and save the investigation — history is visible in entity detail
via ``GET /collab/comments``.

Endpoints (``/api/v1/collab``):

* ``POST /comments``                      — add a comment (extracts mentions, notifies).
* ``GET  /comments``                      — comments on a target (entity detail thread).
* ``POST /comments/{id}/status``          — draft/in_review/resolved/archived (+ assign).
* ``POST /comments/{id}/promote``         — manual promoted-status (§10.8).
* ``POST /investigations``                — create a shared investigation.
* ``GET  /investigations``                — list mine + shared-with-me.
* ``GET  /investigations/{id}``           — detail + its comments.
* ``PATCH /investigations/{id}``          — update status/notes/entities/members/answer.
* ``GET  /notifications``                 — notification center (+ unread count).
* ``POST /notifications/{id}/read``       — mark one read.
* ``POST /notifications/read-all``        — mark all read.
* ``GET  /activity``                      — activity feed (optional project scope).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api_gateway.auth import current_user
from kg_common import get_settings

router = APIRouter(prefix="/api/v1/collab", tags=["collaboration"])

# Graph target types a comment may attach to (§23.32 acceptance).
COMMENT_TARGETS = ("Entity", "Experiment", "Evidence", "Gap", "Answer", "Investigation")

_cache: dict[str, Any] = {}


def _store():  # type: ignore[no-untyped-def]
    """Lazily build the shared collaboration store (sqlite under runtime_dir)."""
    if "store" not in _cache:
        from kg_common.storage.collaboration import CollaborationStore

        cs = CollaborationStore(f"sqlite:///{get_settings().runtime_dir}/collaboration.db")
        cs.migrate()
        _cache["store"] = cs
    return _cache["store"]


# --------------------------------------------------------------------------- #
# Request bodies                                                               #
# --------------------------------------------------------------------------- #
class CommentBody(BaseModel):
    target_type: str
    target_id: str
    body: str
    parent_id: str = ""
    investigation_id: str = ""
    project: str = ""


class StatusBody(BaseModel):
    status: str
    assignee: str = ""


class PromoteBody(BaseModel):
    promoted: bool = True


class InvestigationBody(BaseModel):
    title: str
    notes: str = ""
    project: str = ""
    entities: list[Any] = []
    filters: dict[str, Any] = {}
    view: dict[str, Any] = {}
    members: list[str] = []


class InvestigationPatch(BaseModel):
    title: str | None = None
    notes: str | None = None
    status: str | None = None
    entities: list[Any] | None = None
    filters: dict[str, Any] | None = None
    view: dict[str, Any] | None = None
    members: list[str] | None = None
    append_answer: dict[str, Any] | None = None


# --------------------------------------------------------------------------- #
# Comments                                                                     #
# --------------------------------------------------------------------------- #
@router.post("/comments")
def add_comment(body: CommentBody, user: str = Depends(current_user)) -> dict:
    """Add a comment to a graph target; extracts @mentions and fans out notices."""
    if body.target_type not in COMMENT_TARGETS:
        raise HTTPException(status_code=400, detail=f"target_type must be one of {COMMENT_TARGETS}")
    if not body.body.strip():
        raise HTTPException(status_code=400, detail="empty comment")
    c = _store().add_comment(
        target_type=body.target_type,
        target_id=body.target_id,
        author=user,
        body=body.body,
        parent_id=body.parent_id,
        investigation_id=body.investigation_id,
        project=body.project,
    )
    return c.as_dict()


@router.get("/comments")
def list_comments(
    target_type: str = Query(...),
    target_id: str = Query(...),
    include_archived: bool = Query(default=True),
    _user: str = Depends(current_user),
) -> dict:
    """List the comment thread on a target (entity detail: «история видна» §23.32)."""
    rows = _store().list_comments(
        target_type=target_type, target_id=target_id, include_archived=include_archived
    )
    return {"comments": [c.as_dict() for c in rows], "count": len(rows)}


@router.post("/comments/{comment_id}/status")
def set_status(comment_id: str, body: StatusBody, user: str = Depends(current_user)) -> dict:
    """Transition a comment's lifecycle (draft/in_review/resolved/archived)."""
    try:
        c = _store().set_comment_status(comment_id, body.status, user, assignee=body.assignee)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if c is None:
        raise HTTPException(status_code=404, detail="comment not found")
    return c.as_dict()


@router.post("/comments/{comment_id}/promote")
def promote(comment_id: str, body: PromoteBody, user: str = Depends(current_user)) -> dict:
    """Manually promote/demote a comment to factual-evidence status (§10.8)."""
    c = _store().promote_comment(comment_id, user, promoted=body.promoted)
    if c is None:
        raise HTTPException(status_code=404, detail="comment not found")
    return c.as_dict()


# --------------------------------------------------------------------------- #
# Investigations                                                               #
# --------------------------------------------------------------------------- #
@router.post("/investigations")
def create_investigation(body: InvestigationBody, user: str = Depends(current_user)) -> dict:
    """Create a shared investigation workspace; notifies invited members."""
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="title required")
    inv = _store().create_investigation(
        owner=user,
        title=body.title,
        notes=body.notes,
        project=body.project,
        entities=body.entities,
        filters=body.filters,
        view=body.view,
        members=body.members,
    )
    return inv.as_dict()


@router.get("/investigations")
def list_investigations(
    all_visible: bool = Query(default=False, description="curator/admin: list all, not just mine"),
    user: str = Depends(current_user),
) -> dict:
    """List investigations the caller owns or is a member of (newest first)."""
    rows = _store().list_investigations(None if all_visible else user)
    return {"investigations": [i.as_dict() for i in rows], "count": len(rows)}


@router.get("/investigations/{investigation_id}")
def get_investigation(investigation_id: str, _user: str = Depends(current_user)) -> dict:
    """Investigation detail plus every comment bound to it."""
    store = _store()
    inv = store.get_investigation(investigation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    comments = store.list_comments_for_investigation(investigation_id)
    out = inv.as_dict()
    out["comments"] = [c.as_dict() for c in comments]
    return out


@router.patch("/investigations/{investigation_id}")
def update_investigation(
    investigation_id: str, body: InvestigationPatch, user: str = Depends(current_user)
) -> dict:
    """Patch an investigation (status/notes/entities/members/append answer)."""
    try:
        inv = _store().update_investigation(
            investigation_id,
            user,
            title=body.title,
            notes=body.notes,
            status=body.status,
            entities=body.entities,
            filters=body.filters,
            view=body.view,
            members=body.members,
            append_answer=body.append_answer,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if inv is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    return inv.as_dict()


# --------------------------------------------------------------------------- #
# Notification center                                                          #
# --------------------------------------------------------------------------- #
@router.get("/notifications")
def notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1000),
    user: str = Depends(current_user),
) -> dict:
    """The caller's notification center + unread badge count."""
    store = _store()
    rows = store.list_notifications(user, unread_only=unread_only, limit=limit)
    return {
        "notifications": [n.as_dict() for n in rows],
        "unread": store.unread_count(user),
        "count": len(rows),
    }


@router.post("/notifications/{notif_id}/read")
def mark_read(notif_id: str, user: str = Depends(current_user)) -> dict:
    """Mark one notification read (scoped to the caller)."""
    ok = _store().mark_read(notif_id, user)
    if not ok:
        raise HTTPException(status_code=404, detail="notification not found")
    return {"ok": True, "unread": _store().unread_count(user)}


@router.post("/notifications/read-all")
def mark_all_read(user: str = Depends(current_user)) -> dict:
    """Mark all of the caller's notifications read."""
    n = _store().mark_all_read(user)
    return {"ok": True, "marked": n, "unread": 0}


# --------------------------------------------------------------------------- #
# Activity feed                                                                #
# --------------------------------------------------------------------------- #
@router.get("/activity")
def activity(
    project: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    _user: str = Depends(current_user),
) -> dict:
    """Recent collaboration activity, optionally scoped to a project/lab."""
    rows = _store().list_activity(project=project, limit=limit)
    return {"activity": [a.as_dict() for a in rows], "count": len(rows)}

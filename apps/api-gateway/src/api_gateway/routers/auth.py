"""Auth + audit endpoints (§19 / §24.14)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api_gateway import audit
from api_gateway.auth import current_role, current_user, issue_token

router = APIRouter(prefix="/api/v1", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    role: str = "researcher"


@router.post("/auth/login")
def login(body: LoginBody) -> dict:
    token = issue_token(body.username, body.role)
    audit.record("login", user=body.username, role=body.role)
    return {"token": token, "token_type": "bearer", "role": body.role}


@router.get("/auth/me")
def me(role: str = Depends(current_role), user: str = Depends(current_user)) -> dict:
    return {"user": user, "role": role}


@router.get("/admin/audit")
def audit_tail(limit: int = 100, role: str = Depends(current_role)) -> dict:
    # only privileged roles can read the audit log
    if role not in {"admin", "project_manager", "curator"}:
        return {"entries": [], "note": "insufficient role for audit log"}
    return {"entries": audit.tail(limit)}

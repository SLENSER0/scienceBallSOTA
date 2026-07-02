"""Notification/subscription endpoints (§24.16)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api_gateway import subscriptions
from api_gateway.auth import current_role, current_user
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class SubscribeBody(BaseModel):
    topic: str
    channels: list[str] | None = None


@router.post("/subscribe")
def subscribe(body: SubscribeBody, user: str = Depends(current_user)) -> dict:
    return subscriptions.subscribe(user, body.topic, body.channels)


@router.get("/subscriptions")
def list_subscriptions(user: str = Depends(current_user)) -> dict:
    return {"subscriptions": subscriptions.list_for(user)}


@router.get("")
def notifications(user: str = Depends(current_user), role: str = Depends(current_role)) -> dict:
    return {"notifications": subscriptions.notifications_for(user, get_store(), role=role)}

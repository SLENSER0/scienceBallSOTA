"""§13.21 Human-in-the-loop clarification for chat — уточнение сущности в диалоге.

Sits alongside :mod:`api_gateway.routers.chat`. Before a user turn is answered the
UI asks this router whether the question hides an **ambiguous critical entity**; if
so the agent *pauses* and returns the clarification the human must resolve, instead
of guessing (§13.21). Once the human picks an option the resume endpoint folds the
choice into the question, runs the agent, and persists the turn into the chat
session exactly like a normal message — so the existing ``…/stream`` endpoint
replays the grounded answer with no further wiring.

Flow (§13.21):

1. ``POST /api/v1/chat/clarify/check`` — ``{content, session_id?}`` → either
   ``{status:"ok"}`` (answer directly, no ambiguity) or ``{status:"clarify",
   clarify_id, mention, request}`` where ``request`` carries the question, the
   option ids and human-readable candidates.
2. ``POST /api/v1/chat/clarify/resume`` — ``{clarify_id, resume_value}`` → validates
   the choice, re-runs the agent on the disambiguated question, stores the user +
   assistant messages, and returns ``{message_id, stream_url}``.

The ``ENABLE_HITL`` env flag (default on) mirrors §13.21: when off, ``check`` always
returns ``{status:"ok"}`` so batch / eval runs never stop to ask.
"""

from __future__ import annotations

import os
import uuid
from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api_gateway.auth import current_role, current_user
from kg_common import get_settings

router = APIRouter(prefix="/api/v1/chat/clarify", tags=["chat", "hitl"])

# Bounded per-process store of pending clarifications (clarify_id → context).
# LRU-capped so a stream of abandoned clarifications cannot grow without bound.
_PENDING: OrderedDict[str, dict[str, Any]] = OrderedDict()
_PENDING_MAX = 512

# Shared lazy ChatStore, mirroring routers/chat.py so both persist to one db.
_cache: dict[str, object] = {}


def _hitl_enabled() -> bool:
    """§13.21 feature flag — ``ENABLE_HITL`` (default on; ``0``/``false``/``no`` off)."""
    return os.environ.get("ENABLE_HITL", "1").strip().lower() not in {"0", "false", "no", ""}


def _chat():  # type: ignore[no-untyped-def]
    """Return the migrated :class:`ChatStore` (same db as routers/chat.py)."""
    if "store" not in _cache:
        from kg_common.storage.chat_sessions import ChatStore

        cs = ChatStore(f"sqlite:///{get_settings().runtime_dir}/chat.db")
        cs.migrate()
        _cache["store"] = cs
    return _cache["store"]


def _remember(ctx: dict[str, Any]) -> str:
    """Store a pending clarification and return its id, evicting the oldest if full."""
    clarify_id = f"clr:{uuid.uuid4().hex[:12]}"
    _PENDING[clarify_id] = ctx
    while len(_PENDING) > _PENDING_MAX:
        _PENDING.popitem(last=False)
    return clarify_id


def _owned_session(sid: str, user: str) -> None:
    """Raise 404 unless ``sid`` exists and is owned by ``user`` (never leak, §19)."""
    sess = _chat().get_session(sid)
    if sess is None or sess.user_id != user:
        raise HTTPException(status_code=404, detail="session not found")


# -- request bodies --------------------------------------------------------
class CheckBody(BaseModel):
    """POST /check — the pending user turn plus its optional chat session."""

    content: str
    session_id: str | None = None


class ResumeBody(BaseModel):
    """POST /resume — the pending clarification id and the human's chosen option."""

    clarify_id: str
    resume_value: str


# -- endpoints -------------------------------------------------------------
@router.post("/check")
def check(
    body: CheckBody,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict[str, Any]:
    """Decide whether the turn needs a §13.21 clarification before it is answered.

    Returns ``{status:"ok"}`` when the question is unambiguous (or ``ENABLE_HITL`` is
    off) — the UI then posts the message normally. Otherwise returns
    ``{status:"clarify", …}`` and holds the context until :func:`resume`.
    """
    if body.session_id:
        _owned_session(body.session_id, user)

    if not _hitl_enabled():
        return {"status": "ok"}

    from agent_service.hitl_chat import find_clarification

    from api_gateway.deps import get_store

    outcome = find_clarification(get_store(), body.content)
    if outcome is None:
        return {"status": "ok"}

    clarify_id = _remember(
        {
            "content": body.content,
            "session_id": body.session_id,
            "role": role,
            "user": user,
            "outcome": outcome,
        }
    )
    return {
        "status": "clarify",
        "clarify_id": clarify_id,
        "mention": outcome.mention,
        "request": outcome.request.as_dict(),
    }


@router.post("/resume")
def resume(
    body: ResumeBody,
    user: str = Depends(current_user),
) -> dict[str, Any]:
    """Continue the paused agent with the human's choice (§13.21 resume).

    Rebuilds the disambiguated question, runs the agent, and — when the clarification
    was raised inside a chat session — stores the original user turn and the grounded
    assistant answer so the existing ``…/stream`` endpoint can replay it.
    """
    ctx = _PENDING.pop(body.clarify_id, None)
    if ctx is None:
        raise HTTPException(status_code=404, detail="clarification not found or expired")
    if ctx["user"] != user:
        raise HTTPException(status_code=404, detail="clarification not found or expired")

    from agent_service.agent import answer_query
    from agent_service.hitl_chat import resume_query

    from api_gateway.deps import get_store

    try:
        clarified = resume_query(ctx["content"], ctx["outcome"], body.resume_value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    payload = answer_query(clarified, get_store(), role=ctx["role"], use_llm=True)

    session_id = ctx.get("session_id")
    if not session_id:
        # No session context: return the answer inline for a one-shot clarify+answer.
        return {"status": "answered", "answer": payload.model_dump(by_alias=True)}

    store = _chat()
    _owned_session(session_id, user)
    store.add_message(session_id, "user", ctx["content"], f"msg:{uuid.uuid4().hex[:12]}")
    asst_mid = f"msg:{uuid.uuid4().hex[:12]}"
    store.add_message(
        session_id, "assistant", payload.model_dump_json(by_alias=True), asst_mid
    )
    return {
        "status": "answered",
        "message_id": asst_mid,
        "stream_url": f"/api/v1/chat/sessions/{session_id}/stream?message_id={asst_mid}",
    }

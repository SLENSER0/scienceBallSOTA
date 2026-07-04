"""Chat-session endpoints — чат-сессии ассистента (§14.4 / §5.3).

Sessions and their ordered messages are persisted via
:class:`~kg_common.storage.chat_sessions.ChatStore` (SQLite at
``runtime_dir/chat.db``, lazily migrated like :mod:`api_gateway.routers.views`).
A user turn runs the agent *in-process* (:func:`agent_service.agent.answer_query`)
and the structured :class:`~kg_common.AnswerPayload` — answer plus its artifacts
(citations, gaps, graph, table) — is stored as the assistant message. The
``/stream`` endpoint *replays* that stored payload as typed Server-Sent Events in
the §5.3 format (``event: <type>`` + ``data: <json>``), and ``/export`` renders
the same report as JSON or Markdown. Ownership is strict: a session that is
missing **or** owned by another user is reported as ``404`` so foreign sessions
never leak (§19).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from api_gateway.auth import current_role, current_user
from kg_common import AnswerPayload, get_settings

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

# Lazy per-process ChatStore (same pattern as routers/views.py).
_cache: dict[str, object] = {}


def _chat():  # type: ignore[no-untyped-def]
    """Return the migrated :class:`ChatStore`, opening it once per process."""
    if "store" not in _cache:
        from kg_common.storage.chat_sessions import ChatStore

        cs = ChatStore(f"sqlite:///{get_settings().runtime_dir}/chat.db")
        cs.migrate()
        _cache["store"] = cs
    return _cache["store"]


# -- request bodies --------------------------------------------------------
class SessionBody(BaseModel):
    """POST /sessions payload — заголовок и произвольные метаданные."""

    title: str = ""
    metadata: dict[str, Any] = {}  # accepted; no column in §14.4 schema


class MessageBody(BaseModel):
    """POST /sessions/{sid}/messages payload — текст и вложения."""

    content: str
    attachments: list[dict[str, Any]] = []  # accepted; not persisted separately


# -- SSE + helpers ---------------------------------------------------------
def _sse(event_type: str, data: dict) -> bytes:
    """SSE-фрейм / SSE frame — ``event: <type>`` + ``data: <json>`` (§5.3)."""
    body = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {body}\n\n".encode()


def _chunks(text: str, size: int = 40) -> Iterator[str]:
    """Split answer text into streamable token chunks (≥1 chunk if non-empty)."""
    text = text or ""
    for i in range(0, len(text), size):
        yield text[i : i + size]


def _resolve_user(authorization: str | None, access_token: str | None) -> str:
    """Resolve the caller for SSE endpoints.

    Browsers' ``EventSource`` cannot attach an ``Authorization`` header, so
    token-authorized SSE clients pass the bearer as an ``?access_token=`` query
    parameter instead (the same convention used by other streaming surfaces).
    We fold it into a synthetic ``Bearer`` header when no real one is present,
    then reuse the shared :func:`current_user` resolution.
    """
    if access_token and not (authorization and authorization.lower().startswith("bearer ")):
        authorization = f"Bearer {access_token}"
    return current_user(authorization)


def _owned_session(sid: str, user: str):  # type: ignore[no-untyped-def]
    """Return the caller's own session or raise 404 (never leak a foreign one)."""
    sess = _chat().get_session(sid)
    if sess is None or sess.user_id != user:
        raise HTTPException(status_code=404, detail="session not found")
    return sess


def _load_answer(sid: str, message_id: str) -> AnswerPayload:
    """Load the stored assistant :class:`AnswerPayload` for ``message_id`` (404 if none)."""
    for m in _chat().messages(sid):
        if m.message_id == message_id and m.role == "assistant":
            return AnswerPayload.model_validate_json(m.content)
    raise HTTPException(status_code=404, detail="message not found")


def _report(payload: AnswerPayload) -> dict[str, Any]:
    """Reduce a payload to the exportable report — резюме/доказательства/пробелы."""
    return {
        "summary": payload.answer_markdown,
        "evidence": [c.model_dump(by_alias=True) for c in payload.citations],
        "gaps": payload.gaps,
    }


def _report_markdown(report: dict[str, Any]) -> str:
    """Render the report as Markdown (RU/EN headings)."""
    lines = ["# Отчёт / Report", "", "## Резюме / Summary", report["summary"], ""]
    lines.append("## Доказательства / Evidence")
    for c in report["evidence"]:
        marker = c.get("marker", "")
        title = c.get("sourceTitle") or ""
        text = (c.get("evidence") or {}).get("text") or ""
        lines.append(f"- {marker} {title} — {text}".rstrip(" —").rstrip())
    lines += ["", "## Пробелы / Gaps"]
    for g in report["gaps"]:
        lines.append(f"- {g.get('about') or g.get('id') or g}")
    return "\n".join(lines) + "\n"


# -- endpoints -------------------------------------------------------------
@router.post("/sessions")
def create_session(body: SessionBody, user: str = Depends(current_user)) -> dict:
    """Create a new chat session owned by the caller (§14.4)."""
    sid = f"chat:{uuid.uuid4().hex[:12]}"
    sess = _chat().create_session(sid, user_id=user, title=body.title)
    return {
        "session_id": sess.session_id,
        "created_at": sess.created_at,
        "user_id": sess.user_id,
    }


@router.get("/sessions")
def list_sessions(
    user: str = Depends(current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """List the caller's own sessions, newest first, with limit/offset paging."""
    store = _chat()
    sessions = list(reversed(store.list_sessions(user)))  # store is oldest-first
    window = sessions[offset : offset + limit]
    items = []
    for s in window:
        msgs = store.messages(s.session_id)
        last_at = msgs[-1].created_at if msgs else s.created_at
        items.append(
            {
                "session_id": s.session_id,
                "title": s.title,
                "created_at": s.created_at,
                "last_message_at": last_at,
            }
        )
    return {"sessions": items, "count": len(items)}


@router.get("/sessions/{sid}")
def get_session(sid: str, user: str = Depends(current_user)) -> dict:
    """Return one owned session with its full message history (404 if foreign/missing)."""
    _owned_session(sid, user)
    msgs = _chat().messages(sid)
    return {"session_id": sid, "messages": [m.as_dict() for m in msgs]}


@router.post("/sessions/{sid}/messages")
def post_message(
    sid: str,
    body: MessageBody,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """Persist the user turn, run the agent in-process, store the answer + artifacts."""
    _owned_session(sid, user)
    from agent_service.agent import answer_query

    from api_gateway.deps import get_store

    store = _chat()
    user_mid = f"msg:{uuid.uuid4().hex[:12]}"
    store.add_message(sid, "user", body.content, user_mid)

    payload = answer_query(body.content, get_store(), role=role, use_llm=True)
    asst_mid = f"msg:{uuid.uuid4().hex[:12]}"
    # the full AnswerPayload JSON carries the answer *and* its artifacts (§5.3)
    store.add_message(sid, "assistant", payload.model_dump_json(by_alias=True), asst_mid)

    return {
        "message_id": asst_mid,
        "stream_url": f"/api/v1/chat/sessions/{sid}/stream?message_id={asst_mid}",
    }


@router.get("/sessions/{sid}/stream")
def stream(
    sid: str,
    message_id: str,
    access_token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    """Replay a stored assistant answer as typed SSE events (§5.3 format).

    Accepts the bearer token via the ``?access_token=`` query parameter because
    ``EventSource`` cannot send an ``Authorization`` header; ownership is still
    enforced so foreign sessions never leak (§19).
    """
    user = _resolve_user(authorization, access_token)
    _owned_session(sid, user)
    payload = _load_answer(sid, message_id)

    def gen() -> Iterator[bytes]:
        # Reasoning-capable models expose their chain-of-thought — stream it first
        # so the UI shows a «thinking» panel before the answer (§5.3, open-webui style).
        if payload.reasoning:
            yield _sse("reasoning", {"text": payload.reasoning})
        for chunk in _chunks(payload.answer_markdown):
            yield _sse("token", {"text": chunk})
        yield _sse(
            "evidence",
            {"citations": [c.model_dump(by_alias=True) for c in payload.citations]},
        )
        for g in payload.gaps:
            yield _sse("gap", g)
        if payload.graph:
            yield _sse("graph", payload.graph.model_dump(by_alias=True))
        if payload.table:
            yield _sse("table", payload.table)
        # error-free terminating event
        yield _sse("done", {"confidence": payload.confidence, "models": payload.used_models})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/sessions/{sid}/messages/{mid}/export")
def export_message(
    sid: str,
    mid: str,
    format: str = "json",
    user: str = Depends(current_user),
) -> Any:
    """Export the stored answer report as JSON or Markdown (404 if foreign/missing)."""
    _owned_session(sid, user)
    report = _report(_load_answer(sid, mid))
    if format == "md":
        return PlainTextResponse(_report_markdown(report), media_type="text/markdown")
    return report

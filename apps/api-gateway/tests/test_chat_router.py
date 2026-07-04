"""Chat-session router tests (§14.4). Hermetic: the agent call is monkeypatched.

The agent (:func:`agent_service.agent.answer_query`) and the graph store
(:func:`api_gateway.deps.get_store`) are replaced so no Kuzu/LLM is touched —
the router persists a *canned* :class:`AnswerPayload`, then we exercise the
session/list/history/stream/export/ownership surface end-to-end.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kg_common import AnswerPayload, Citation, EvidenceRef

CANNED_ANSWER = (
    "Обратный осмос эффективно удаляет сульфаты из воды. "
    "Reverse osmosis removes sulfates efficiently."
)


def _canned() -> AnswerPayload:
    """A deterministic answer standing in for the real agent output."""
    return AnswerPayload(
        answer_markdown=CANNED_ANSWER,
        citations=[
            Citation(
                marker="[1]",
                evidence=EvidenceRef(
                    evidence_id="ev:1", source_id="src:1", text="RO 99% rejection", page=3
                ),
                source_title="RO desalination study",
                year=2021,
            )
        ],
        gaps=[{"id": "gap:1", "about": "нет данных по стоимости / no cost data"}],
        confidence=0.88,
        used_models=["synth-oss"],
    )


@pytest.fixture(scope="module")
def client(tmp_path_factory):  # type: ignore[no-untyped-def]
    import agent_service.agent as agent_mod
    import api_gateway.deps as deps
    import api_gateway.routers.chat as chat

    from kg_common.config import get_settings

    # point the chat.db + agent at hermetic stand-ins
    d = tmp_path_factory.mktemp("chat")
    get_settings().runtime_dir = str(d)
    Path(d).mkdir(parents=True, exist_ok=True)
    chat._cache.clear()

    orig_answer = agent_mod.answer_query
    orig_store = deps.get_store
    agent_mod.answer_query = lambda *a, **k: _canned()
    deps.get_store = lambda: None  # ignored by the patched agent

    from api_gateway.main import create_app

    app = create_app()
    # the parent wires this into attach_routers; mount it here if not yet present
    if not any(getattr(r, "path", "").startswith("/api/v1/chat/sessions") for r in app.routes):
        app.include_router(chat.router)

    yield TestClient(app)

    agent_mod.answer_query = orig_answer
    deps.get_store = orig_store
    chat._cache.clear()


def _login(client: TestClient, username: str, role: str = "researcher") -> dict[str, str]:
    tok = client.post("/api/v1/auth/login", json={"username": username, "role": role}).json()[
        "token"
    ]
    return {"Authorization": f"Bearer {tok}"}


def _new_session(client: TestClient, headers: dict[str, str], title: str = "T") -> str:
    return client.post("/api/v1/chat/sessions", json={"title": title}, headers=headers).json()[
        "session_id"
    ]


def _new_message(client: TestClient, headers: dict[str, str], sid: str, content: str = "q") -> str:
    return client.post(
        f"/api/v1/chat/sessions/{sid}/messages", json={"content": content}, headers=headers
    ).json()["message_id"]


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """Parse ``event: <t>\\ndata: <json>`` frames into (type, data) tuples."""
    frames: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        etype: str | None = None
        data: dict = {}
        for line in block.splitlines():
            if line.startswith("event: "):
                etype = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if etype is not None:
            frames.append((etype, data))
    return frames


def test_create_session_returns_ids(client: TestClient) -> None:
    h = _login(client, "alice")
    r = client.post("/api/v1/chat/sessions", json={"title": "T1"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"].startswith("chat:")
    assert body["user_id"] == "alice"
    assert body["created_at"]


def test_list_sessions_only_own(client: TestClient) -> None:
    ha = _login(client, "bob")
    hb = _login(client, "carol")
    sid = _new_session(client, ha, "bobs")
    a_list = client.get("/api/v1/chat/sessions", headers=ha).json()["sessions"]
    assert any(s["session_id"] == sid for s in a_list)
    # a second user cannot see bob's session in their list …
    b_list = client.get("/api/v1/chat/sessions", headers=hb).json()["sessions"]
    assert all(s["session_id"] != sid for s in b_list)
    # … nor fetch it directly (foreign -> 404, never leak)
    assert client.get(f"/api/v1/chat/sessions/{sid}", headers=hb).status_code == 404


def test_list_item_fields(client: TestClient) -> None:
    h = _login(client, "dave")
    sid = _new_session(client, h, "D")
    lst = client.get("/api/v1/chat/sessions", headers=h).json()["sessions"]
    item = next(s for s in lst if s["session_id"] == sid)
    assert set(item) == {"session_id", "title", "created_at", "last_message_at"}
    assert item["title"] == "D"


def test_list_newest_first_and_paging(client: TestClient) -> None:
    h = _login(client, "erin")
    s1 = _new_session(client, h, "one")
    time.sleep(0.01)  # guarantee a distinct created_at
    s2 = _new_session(client, h, "two")
    listed = client.get("/api/v1/chat/sessions", headers=h).json()["sessions"]
    ids = [s["session_id"] for s in listed]
    assert ids.index(s2) < ids.index(s1)  # newest first
    top = client.get("/api/v1/chat/sessions", params={"limit": 1}, headers=h).json()["sessions"]
    assert len(top) == 1 and top[0]["session_id"] == s2
    nxt = client.get("/api/v1/chat/sessions", params={"limit": 1, "offset": 1}, headers=h).json()[
        "sessions"
    ]
    assert nxt[0]["session_id"] == s1


def test_list_last_message_at_reflects_last_turn(client: TestClient) -> None:
    """list_sessions' batched last_message_at == the session's last message created_at."""
    h = _login(client, "quinn")
    empty_sid = _new_session(client, h, "empty")
    active_sid = _new_session(client, h, "active")
    _new_message(client, h, active_sid, "первый вопрос")

    hist = client.get(f"/api/v1/chat/sessions/{active_sid}", headers=h).json()["messages"]
    last_msg_at = hist[-1]["created_at"]

    listed = client.get("/api/v1/chat/sessions", headers=h).json()["sessions"]
    by_id = {s["session_id"]: s for s in listed}
    # session with messages -> last_message_at is the last turn's timestamp
    assert by_id[active_sid]["last_message_at"] == last_msg_at
    # empty session -> falls back to the session's own created_at
    assert by_id[empty_sid]["last_message_at"] == by_id[empty_sid]["created_at"]


def test_post_message_persists(client: TestClient) -> None:
    h = _login(client, "frank")
    sid = _new_session(client, h, "F")
    r = client.post(
        f"/api/v1/chat/sessions/{sid}/messages",
        json={"content": "как обессолить воду?"},
        headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["message_id"].startswith("msg:")
    assert body["stream_url"] == (
        f"/api/v1/chat/sessions/{sid}/stream?message_id={body['message_id']}"
    )
    # history holds the user turn then the assistant turn, in order
    hist = client.get(f"/api/v1/chat/sessions/{sid}", headers=h).json()["messages"]
    assert [m["role"] for m in hist] == ["user", "assistant"]
    assert hist[0]["content"] == "как обессолить воду?"
    assert hist[1]["message_id"] == body["message_id"]


def test_post_message_foreign_session_404(client: TestClient) -> None:
    ha = _login(client, "gina")
    hb = _login(client, "hugo")
    sid = _new_session(client, ha, "G")
    r = client.post(f"/api/v1/chat/sessions/{sid}/messages", json={"content": "x"}, headers=hb)
    assert r.status_code == 404


def test_stream_replays_tokens_and_evidence(client: TestClient) -> None:
    h = _login(client, "ivan")
    sid = _new_session(client, h, "I")
    mid = _new_message(client, h, sid, "вопрос")
    r = client.get(f"/api/v1/chat/sessions/{sid}/stream", params={"message_id": mid}, headers=h)
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    frames = _parse_sse(r.text)
    types = [t for t, _ in frames]
    assert types.count("token") >= 1  # >=1 token line
    assert "evidence" in types  # evidence line present
    tok = next(d for t, d in frames if t == "token")
    assert tok.get("text")
    ev = next(d for t, d in frames if t == "evidence")
    assert ev["citations"] and ev["citations"][0]["marker"] == "[1]"


def test_stream_foreign_session_404(client: TestClient) -> None:
    ha = _login(client, "nick")
    hb = _login(client, "olga")
    sid = _new_session(client, ha, "N")
    mid = _new_message(client, ha, sid)
    r = client.get(f"/api/v1/chat/sessions/{sid}/stream", params={"message_id": mid}, headers=hb)
    assert r.status_code == 404


def test_export_json(client: TestClient) -> None:
    h = _login(client, "jane")
    sid = _new_session(client, h, "J")
    mid = _new_message(client, h, sid)
    r = client.get(
        f"/api/v1/chat/sessions/{sid}/messages/{mid}/export",
        params={"format": "json"},
        headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"summary", "evidence", "gaps"}
    assert body["summary"] == CANNED_ANSWER
    assert body["evidence"][0]["marker"] == "[1]"
    assert body["gaps"][0]["id"] == "gap:1"


def test_export_markdown(client: TestClient) -> None:
    h = _login(client, "kate")
    sid = _new_session(client, h, "K")
    mid = _new_message(client, h, sid)
    r = client.get(
        f"/api/v1/chat/sessions/{sid}/messages/{mid}/export",
        params={"format": "md"},
        headers=h,
    )
    assert r.status_code == 200
    assert "text/markdown" in r.headers["content-type"]
    assert "## Резюме / Summary" in r.text
    assert "Обратный осмос" in r.text  # canned summary content
    assert "[1]" in r.text  # citation marker rendered


def test_export_foreign_message_404(client: TestClient) -> None:
    ha = _login(client, "leo")
    hb = _login(client, "mona")
    sid = _new_session(client, ha, "L")
    mid = _new_message(client, ha, sid)
    r = client.get(
        f"/api/v1/chat/sessions/{sid}/messages/{mid}/export",
        params={"format": "json"},
        headers=hb,
    )
    assert r.status_code == 404


def test_get_missing_session_404(client: TestClient) -> None:
    h = _login(client, "pete")
    assert client.get("/api/v1/chat/sessions/chat:nope", headers=h).status_code == 404

"""Query / chat endpoints (§14 / §5.3)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api_gateway import audit
from api_gateway.auth import current_role, current_user
from api_gateway.deps import get_store
from kg_common import AnswerPayload

router = APIRouter(prefix="/api/v1", tags=["query"])


class QueryRequest(BaseModel):
    query: str
    role: str = "researcher"
    use_llm: bool = True
    # Explicit geographic filter — отечественная/зарубежная практика (§ гео-фильтр).
    geography: str | None = None  # russia | cis | foreign | global | all | None


@router.post("/query", response_model=AnswerPayload)
def query(
    req: QueryRequest,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> AnswerPayload:
    from agent_service.agent import answer_query

    audit.record("query", user=user, role=role, detail={"q": req.query[:200], "geo": req.geography})
    return answer_query(
        req.query, get_store(), role=role, use_llm=req.use_llm, geography=req.geography
    )


@router.post("/query/stream")
async def query_stream(req: QueryRequest, role: str = Depends(current_role)) -> StreamingResponse:
    """Server-sent events: retrieval artifacts arrive first, then the answer streams
    token-by-token (§5.3) so a brief conclusion appears in seconds and fills in live."""
    from agent_service.agent import answer_query_stream
    from starlette.concurrency import run_in_threadpool

    async def gen() -> AsyncIterator[bytes]:
        _sentinel = object()
        try:
            it = answer_query_stream(
                req.query, get_store(), role=role, geography=req.geography
            )
            while True:
                item = await run_in_threadpool(next, it, _sentinel)
                if item is _sentinel:
                    break
                kind, data = item
                if kind == "meta":
                    if data.get("graph"):
                        yield _sse("graph", data["graph"].model_dump(by_alias=True))
                    if data.get("table"):
                        yield _sse("table", data["table"])
                    for g in data.get("gaps", []):
                        yield _sse("gap", g)
                    yield _sse(
                        "evidence",
                        {"citations": [c.model_dump(by_alias=True) for c in data["citations"]]},
                    )
                elif kind == "brief":
                    yield _sse("brief", {"text": data["text"]})
                elif kind == "token":
                    yield _sse("token", {"text": data})
                elif kind == "final":
                    yield _sse(
                        "done",
                        {"confidence": data["confidence"], "models": data["used_models"]},
                    )
        except (
            Exception
        ) as exc:  # surface mid-stream failures as an error event (finding query.py:43)
            yield _sse("error", {"message": str(exc)[:300]})

    return StreamingResponse(gen(), media_type="text/event-stream")


def _sse(event_type: str, data: dict) -> bytes:
    """SSE frame in the shared ``event: <name>`` + ``data: <json>`` contract (§5.3).

    Matches every other streaming router (chat / advise / research) so ``EventSource``
    named-event listeners fire correctly.
    """
    body = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {body}\n\n".encode()

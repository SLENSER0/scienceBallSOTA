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


@router.post("/query", response_model=AnswerPayload)
def query(
    req: QueryRequest,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> AnswerPayload:
    from agent_service.agent import answer_query

    audit.record("query", user=user, role=role, detail={"q": req.query[:200]})
    return answer_query(req.query, get_store(), role=role, use_llm=req.use_llm)


@router.post("/query/stream")
async def query_stream(req: QueryRequest, role: str = Depends(current_role)) -> StreamingResponse:
    """Server-sent events: emits parse/retrieve/answer stages (§5.3 ChatStreamEvent)."""
    from agent_service.agent import answer_query

    from kg_extractors.query_parser import parse_query

    async def gen() -> AsyncIterator[bytes]:
        intent = parse_query(req.query)
        yield _sse("tool_start", {"tool": "parse", "intent": intent.to_dict()})
        ans = answer_query(req.query, get_store(), role=role, use_llm=req.use_llm)
        if ans.graph:
            yield _sse("graph", ans.graph.model_dump(by_alias=True))
        if ans.table:
            yield _sse("table", ans.table)
        for g in ans.gaps:
            yield _sse("gap", g)
        yield _sse("token", {"text": ans.answer_markdown})
        yield _sse("evidence", {"citations": [c.model_dump(by_alias=True) for c in ans.citations]})
        yield _sse("done", {"confidence": ans.confidence, "models": ans.used_models})

    return StreamingResponse(gen(), media_type="text/event-stream")


def _sse(event_type: str, data: dict) -> bytes:
    payload = {"type": event_type, "data": data}
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n".encode()

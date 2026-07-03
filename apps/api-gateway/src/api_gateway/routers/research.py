"""Article discovery + manual ingestion — the «Библиотека» surface (§5 / library).

- ``GET  /research/sources``     — the scientific source catalog (ResearchGate,
  eLIBRARY, Springer, Google Patents, MDPI, CyberLeninka, Wiley, ScienceDirect,
  Sci-Hub — the last flagged as a shadow library, link-only).
- ``POST /research/plan``        — deep-research: decompose a question into
  sub-questions × ready-to-open per-source search links (OSS-LLM optional).
- ``POST /research/articles``    — manually add an article to the graph as a
  ``:Paper`` (+ abstract chunk/evidence); curator/admin/researcher only.
- ``GET  /research/articles``    — recently manually-added papers.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api_gateway.auth import current_role, current_user
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/research", tags=["research"])

_CAN_ADD = {"admin", "curator", "researcher", "analyst", "project_manager"}


class PlanBody(BaseModel):
    question: str
    source_ids: list[str] | None = None
    use_llm: bool = False


class ArticleBody(BaseModel):
    title: str
    authors: list[str] = []
    year: int | None = None
    doi: str = ""
    url: str = ""
    source: str = "manual"
    abstract: str = ""
    domain: str = ""


@router.get("/sources")
def sources() -> dict:
    """The external scientific-source catalog (link-only; no scraping)."""
    from kg_common.research_sources import all_sources

    return {"sources": all_sources()}


@router.post("/plan")
def plan(body: PlanBody) -> dict:
    """Source-catalog plan: sub-questions × per-source search links (fast, offline)."""
    from kg_common.deep_research import build_plan

    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question is required")
    return build_plan(body.question, source_ids=body.source_ids, use_llm=body.use_llm).as_dict()


@router.get("/deep/status")
def deep_status() -> dict:
    """Whether the real open_deep_research engine is available (package + OSS key)."""
    from api_gateway.deep_researcher_runner import deep_research_available

    return {"available": deep_research_available(), "engine": "open_deep_research"}


@router.post("/deep")
async def deep(body: PlanBody, role: str = Depends(current_role)) -> dict:
    """Run the REAL open_deep_research graph on our OSS LLM; return its report.

    Falls back to the source-catalog plan when the engine is unavailable, so the
    endpoint always returns something usable.
    """
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question is required")
    from api_gateway.deep_researcher_runner import deep_research_available, run_deep_research

    if deep_research_available():
        try:
            return await run_deep_research(body.question)
        except Exception as exc:
            from kg_common import get_logger

            get_logger("research").warning("deep_research.failed", error=str(exc)[:200])
    from kg_common.deep_research import build_plan

    return {
        "question": body.question,
        "report": "",
        "engine": "source-catalog-fallback",
        "plan": build_plan(body.question, source_ids=body.source_ids).as_dict(),
    }


def _sse(event: str, data: dict) -> bytes:
    body = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {body}\n\n".encode()


@router.get("/deep/stream")
async def deep_stream(
    question: str = Query(min_length=1), role: str = Depends(current_role)
) -> StreamingResponse:
    """Stream the REAL open_deep_research run as SSE: live stages + reasoning + report.

    Emits ``stage`` (which ODR node ran), ``reasoning`` (its intermediate output),
    ``token`` (live LLM tokens), ``report`` (final), ``done`` — so the UI shows the
    reasoning trace as it happens (open-webui «thinking» pattern).
    """
    from api_gateway.deep_researcher_runner import deep_research_available, stream_deep_research

    async def gen():  # type: ignore[no-untyped-def]
        if not deep_research_available():
            yield _sse("error", {"message": "open_deep_research недоступен"})
            return
        try:
            async for event, data in stream_deep_research(question):
                yield _sse(event, data)
        except Exception as exc:  # surface a failure mid-stream
            yield _sse("error", {"message": str(exc)[:200]})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/articles")
def add_article(
    body: ArticleBody,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """Manually add an article to the graph as a :Paper (+ abstract chunk/evidence)."""
    if role not in _CAN_ADD:
        raise HTTPException(status_code=403, detail="role may not add articles")
    from kg_common.manual_article import ManualArticle, build_graph_ops, validate_article

    art = ManualArticle(
        title=body.title,
        authors=body.authors,
        year=body.year,
        doi=body.doi,
        url=body.url,
        source=body.source,
        abstract=body.abstract,
        domain=body.domain,
    )
    errs = validate_article(art)
    if errs:
        raise HTTPException(status_code=422, detail={"errors": errs})

    ops = build_graph_ops(art)
    store = get_store()
    for node in ops["nodes"]:
        store.upsert_node(node["id"], node["label"], **node["props"])
    for edge in ops["edges"]:
        store.upsert_edge(edge["src"], edge["dst"], edge["type"], **edge["props"])

    from api_gateway import audit

    audit.record("add_article", user=user, role=role, detail={"paper_id": ops["paper_id"]})
    return {"paper_id": ops["paper_id"], "nodes": len(ops["nodes"]), "edges": len(ops["edges"])}


@router.get("/articles")
def recent_articles(limit: int = 20) -> dict:
    """Recently manually-added papers (source=manual/manual_add)."""
    store = get_store()
    rows = store.rows(
        "MATCH (n:Node {label:'Paper'}) WHERE n.extractor_run_id='manual_add' "
        "RETURN n.id, n.name, n.year, n.doi, n.url ORDER BY n.name LIMIT $lim",
        {"lim": int(limit)},
    )
    items: list[dict[str, Any]] = [
        {"id": r[0], "title": r[1], "year": r[2], "doi": r[3], "url": r[4]} for r in rows
    ]
    return {"articles": items, "count": len(items)}

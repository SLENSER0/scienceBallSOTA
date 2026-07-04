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

import asyncio
import contextlib
import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api_gateway.auth import current_role, current_user
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/research", tags=["research"])

_CAN_ADD = {"admin", "curator", "researcher", "analyst", "project_manager"}

# Multimodal deep-research: figure/micrograph/flowsheet/screenshot analysis.
_IMG_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
_IMG_MAX_BYTES = 12 * 1024 * 1024  # 12 MB image cap


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


@router.post("/multimodal")
async def multimodal(
    question: str = Form("Опиши, что изображено, и извлеки все численные данные и обозначения."),
    file: UploadFile = File(...),
    role: str = Depends(current_role),
) -> dict:
    """Analyse an image (figure, micrograph, flowsheet, screenshot) with the OSS
    multimodal model (MiniMax-M3) — the visual leg of multimodal deep-research.

    Returns a structured Russian analysis the researcher can feed into deep-research
    or attach to a manually-added article. Nothing is written to the graph here.
    """
    if role not in _CAN_ADD:
        raise HTTPException(status_code=403, detail="role may not run multimodal analysis")

    import base64
    from pathlib import Path

    suffix = Path(file.filename or "image.png").suffix.lower()
    mime = _IMG_MIME.get(suffix)
    if mime is None:
        raise HTTPException(status_code=415, detail=f"unsupported image type: {suffix or 'none'}")

    raw = await file.read(_IMG_MAX_BYTES + 1)
    if len(raw) > _IMG_MAX_BYTES:
        raise HTTPException(status_code=413, detail="image too large (max 12 MB)")
    data_uri = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"

    from kg_extractors.llm import get_llm

    system = (
        "Ты — научный ассистент по горному делу и металлургии. Проанализируй изображение "
        "и ответь по-русски, структурировано: (1) что изображено; (2) ключевые численные "
        "данные, оси, единицы, подписи; (3) методы/материалы/режимы, если видны; "
        "(4) релевантность к исследовательскому вопросу. Не выдумывай данных, которых нет."
    )
    llm = get_llm()
    try:
        analysis = llm.complete_multimodal(question, [data_uri], system=system, max_tokens=1500)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"multimodal model error: {exc}") from exc

    return {
        "model": llm.used_models[-1] if llm.used_models else None,
        "question": question,
        "filename": file.filename,
        "analysis": analysis,
    }


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
        # Drain the ODR run in a background task and pull events off a queue with a
        # 15s timeout, emitting an SSE keep-alive comment while idle. Deep research
        # can go minutes between events; without this, idle-timeout proxies (nginx,
        # gunicorn, CDNs) sever the connection mid-run (M-24).
        queue: asyncio.Queue = asyncio.Queue()
        end_marker = object()

        async def _produce() -> None:
            try:
                async for event, data in stream_deep_research(question):
                    await queue.put(("event", (event, data)))
            except Exception as exc:  # surface a failure mid-stream
                await queue.put(("error", str(exc)[:200]))
            finally:
                await queue.put((end_marker, None))

        task = asyncio.create_task(_produce())
        try:
            while True:
                try:
                    kind, payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    yield b": keepalive\n\n"  # SSE comment — ignored by EventSource
                    continue
                if kind is end_marker:
                    break
                if kind == "error":
                    yield _sse("error", {"message": payload})
                    break
                event, data = payload
                yield _sse(event, data)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

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


class DeepSource(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""
    year: int | None = None


class PromoteBody(BaseModel):
    sources: list[DeepSource] = []


def _source_summary(s: dict) -> dict:
    return {"title": s.get("title") or s.get("url") or "источник", "url": s.get("url", ""), "year": s.get("year")}


def _assess_source_trust(s: dict) -> dict:
    """Run one found source through Source Trust (retraction/freshness/peer-review)."""
    from datetime import UTC, datetime

    from kg_common.manual_article import ManualArticle, article_id
    from kg_retrievers.citation_trust import assess_citation

    year = s.get("year")
    age_days = None
    if isinstance(year, int) and year > 0:
        age_days = max(0.0, (datetime.now(UTC).year - year) * 365.25)
    pid = article_id(ManualArticle(title=s.get("title", ""), url=s.get("url", "")))
    ct = assess_citation(
        {
            "doc_id": pid,
            "source_status": "active",  # a fresh web source; retraction is set later by curation
            "peer_reviewed": False,  # web sources are not peer-reviewed until proven otherwise
            "age_days": age_days,
            "citation_count": 0,
            "primary": False,
        }
    )
    return {
        "doc_id": pid,
        "trust_score": round(ct.trust_score, 3),
        "trust_tier": ct.trust_tier,
        "freshness": ct.freshness_level,
        "warnings": list(ct.warning_messages),
    }


def _ingest_source(s: dict) -> dict:
    """Load one source into the graph as a :Paper (+ snippet chunk/evidence)."""
    from kg_common.manual_article import ManualArticle, build_graph_ops

    art = ManualArticle(
        title=(s.get("title") or s.get("url") or "источник"),
        year=s.get("year"),
        url=s.get("url", ""),
        abstract=s.get("snippet", ""),
        source="deep-research",
    )
    ops = build_graph_ops(art)
    store = get_store()
    for node in ops["nodes"]:
        props = dict(node["props"])
        if node["label"] == "Paper":
            props.setdefault("source_status", "active")
        store.upsert_node(node["id"], node["label"], **props)
    for edge in ops["edges"]:
        store.upsert_edge(edge["src"], edge["dst"], edge["type"], **edge["props"])
    return {"paper_id": ops["paper_id"], "nodes": len(ops["nodes"]), "edges": len(ops["edges"])}


@router.post("/deep/promote")
def promote_sources(
    body: PromoteBody,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """«Загрузить в граф»: run every deep-research source through Source Trust, then
    ingest high/medium-trust ones and route low/untrusted ones to the review queue."""
    if role not in _CAN_ADD:
        raise HTTPException(status_code=403, detail="role may not add sources")
    from api_gateway import audit, source_review_store

    ingested: list[dict] = []
    review: list[dict] = []
    for src in body.sources:
        s = src.model_dump()
        trust = _assess_source_trust(s)
        if trust["trust_tier"] in ("low", "untrusted"):
            sid = source_review_store.enqueue(s, trust)
            review.append({"id": sid, **_source_summary(s), "trust": trust})
        else:
            res = _ingest_source(s)
            ingested.append({**_source_summary(s), "trust": trust, **res})
    audit.record(
        "promote_sources", user=user, role=role,
        detail={"ingested": len(ingested), "review": len(review)},
    )
    return {"ingested": ingested, "review": review}


@router.get("/sources/pending")
def pending_sources() -> dict:
    """Low-trust sources awaiting the user's add/reject decision (§23.27)."""
    from api_gateway import source_review_store

    return {"items": source_review_store.list_pending()}


@router.post("/sources/{sid}/approve")
def approve_source(
    sid: str,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """Approve a low-trust source → ingest it into the graph."""
    if role not in _CAN_ADD:
        raise HTTPException(status_code=403, detail="role may not approve sources")
    from api_gateway import audit, source_review_store

    it = source_review_store.get(sid)
    if not it or it.get("status") != source_review_store.PENDING:
        raise HTTPException(status_code=404, detail="pending source not found")
    res = _ingest_source(it["source"])
    source_review_store.set_status(sid, source_review_store.APPROVED)
    audit.record("approve_source", user=user, role=role, detail={"id": sid, **res})
    return {"approved": sid, **res}


@router.post("/sources/{sid}/reject")
def reject_source(
    sid: str,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """Reject a low-trust source → drop it (never enters the corpus)."""
    if role not in _CAN_ADD:
        raise HTTPException(status_code=403, detail="role may not reject sources")
    from api_gateway import audit, source_review_store

    it = source_review_store.set_status(sid, source_review_store.REJECTED)
    if not it:
        raise HTTPException(status_code=404, detail="pending source not found")
    audit.record("reject_source", user=user, role=role, detail={"id": sid})
    return {"rejected": sid}


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

"""Article discovery + manual ingestion — the «Библиотека» surface (§5 / library).

- ``GET  /research/sources``     — the scientific source catalog (ResearchGate,
  eLIBRARY, Springer, Google Patents, MDPI, CyberLeninka, Wiley, ScienceDirect,
  Sci-Hub — the last flagged as a shadow library, link-only).
- ``POST /research/analyze`` + ``/run`` — gap-informed research: analyze the corpus
  for gaps, then web-search to close them and synthesize a cited report.
- ``POST /research/articles``    — manually add an article to the graph as a
  ``:Paper`` (+ abstract chunk/evidence); curator/admin/researcher only.
- ``GET  /research/articles``    — recently manually-added papers.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
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


class AnalyzeBody(BaseModel):
    question: str
    image: str | None = None  # optional base64 data URI: data:image/png;base64,...


class RunBody(BaseModel):
    question: str
    queries: list[str] = []


@router.post("/analyze")
def analyze_gaps(body: AnalyzeBody, role: str = Depends(current_role)) -> dict:
    """Step 1 of gap-informed research: enrich (optionally with an image), read what the
    corpus HAS, and return what's MISSING / on-what-to-focus + web-search queries."""
    from api_gateway.gap_research import analyze

    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question is required")
    return analyze(get_store(), body.question, body.image)


@router.post("/run")
def run_research(body: RunBody, role: str = Depends(current_role)) -> dict:
    """Step 2: web-search the focus queries, collect real sources, synthesize a cited
    report. The returned sources feed «Загрузить в граф» → source-trust → review."""
    from api_gateway.gap_research import run

    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question is required")
    return run(body.question, body.queries)


class DeepSource(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""
    year: int | None = None


class PromoteBody(BaseModel):
    sources: list[DeepSource] = []


def _source_summary(s: dict) -> dict:
    return {
        "title": s.get("title") or s.get("url") or "источник",
        "url": s.get("url", ""),
        "year": s.get("year"),
    }


# Domain reputation — a web source's HOST is the strongest trust signal we have (a
# ScienceDirect paper ≠ an Instagram post). Journals/repositories/gov are peer-reviewed &
# authoritative; social / course-notes / glossaries / fake test hosts are low-trust and MUST
# go to review instead of being auto-ingested.
_SCHOLARLY_HOSTS = (
    "sciencedirect.com", "nature.com", "science.org", "mdpi.com", "wiley.com", "springer",
    "tandfonline.com", "doi.org", "ncbi.nlm.nih.gov", "pubmed", "core.ac.uk",
    "researchgate.net", "academia.edu", "cyberleninka.ru", "elibrary.ru", "dissercat.com",
    "rusneb.ru", "rucont.ru", "arxiv.org", "ssrn.com", ".edu",
)
_GOV_HOSTS = ("epa.gov", "congress.gov", ".gov", "gwpc.org", "gtk.fi", "stroyinf.ru", "europa.eu")
_JUNK_HOSTS = (
    "instagram.com", "facebook.com", "youtube.com", "youtu.be", "twitter.com", "x.com",
    "tiktok.com", "pinterest.", "reddit.com", "studylib", "studocu", "studfile", "studopedia",
    "coursehero", "scribd.com", "quizlet", "example.org", "example.com", "citynews",
    "ru-ecology.info", "sustainability-directory", "vk.com", "medium.com", "blogspot",
    "wordpress.com",
)


def _domain_reputation(url: str) -> tuple[str, bool]:
    """(domain_class, peer_reviewed) from the URL host: 'junk' | 'scholarly' | 'gov' | 'unknown'."""
    from urllib.parse import urlparse

    host = (urlparse(url).netloc or url).lower()
    if not host:
        return ("unknown", False)
    if any(d in host for d in _JUNK_HOSTS):
        return ("junk", False)
    if any(d in host for d in _SCHOLARLY_HOSTS):
        return ("scholarly", True)
    if any(d in host for d in _GOV_HOSTS):
        return ("gov", True)
    return ("unknown", False)


def _extract_year(*parts: str | None) -> int | None:
    """Most-recent plausible publication year found in the title / url / snippet."""
    import re
    from datetime import UTC, datetime

    now = datetime.now(UTC).year
    years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", " ".join(p or "" for p in parts))]
    years = [y for y in years if 1950 <= y <= now]
    return max(years) if years else None


def _assess_source_trust(s: dict) -> dict:
    """Source Trust for one found web source — from its DOMAIN reputation (journal/gov vs
    social/course-notes) + an extracted year, not a flat prior. Junk domains route to review."""
    from datetime import UTC, datetime

    from kg_common.manual_article import ManualArticle, article_id
    from kg_retrievers.citation_trust import assess_citation

    url = s.get("url", "")
    dclass, peer = _domain_reputation(url)
    year = s.get("year") or _extract_year(s.get("title"), url, s.get("snippet"))
    age_days = None
    if isinstance(year, int) and year > 0:
        age_days = max(0.0, (datetime.now(UTC).year - year) * 365.25)
    # Domain reputation → a citation-count proxy so scholarly/gov outrank unknown/junk in the
    # shared trust formula (the engine has no host awareness of its own).
    cc = 20 if dclass in ("scholarly", "gov") else 0
    pid = article_id(ManualArticle(title=s.get("title", ""), url=url))
    ct = assess_citation(
        {
            "doc_id": pid,
            "source_status": "active",
            "peer_reviewed": peer,
            "age_days": age_days,
            "citation_count": cc,
            "primary": False,
        },
        # Publication age has annual granularity, not ingest recency: a paper from the last
        # ~2 years is fresh; only >~5 years is stale. Without year-scaled thresholds the shared
        # 30/180-day ingest defaults flag every non-current-year paper as «устарел» (red + false
        # stale warning), which would gut the whole source-trust review on the demo path.
        fresh_days=730,
        stale_days=1826,
    )
    tier, score = ct.trust_tier, ct.trust_score
    warnings = list(ct.warning_messages)
    if dclass == "junk":
        # not a scholarly source (social / course-notes / glossary / blog) → force to review.
        # Prepend (don't replace) so the curator keeps the real signals (stale / unreviewed).
        tier, score = "low", min(score, 0.2)
        warnings = ["источник не научный (соцсети/конспекты/блог) — требует ревью", *warnings]
    elif dclass == "unknown" and tier in ("medium", "high"):
        # Host isn't a known journal/repository/gov domain — we can't vouch for it, so it must
        # not auto-ingest: cap to low → routes to review with the reason shown (year alone is
        # too weak a signal to trust an unknown site).
        tier, score = "low", min(score, 0.35)
        warnings = ["источник с неизвестного домена — проверьте вручную", *warnings]
    return {
        "doc_id": pid,
        "trust_score": round(score, 3),
        "trust_tier": tier,
        "freshness": ct.freshness_level,
        "domain": dclass,
        "year": year,
        "warnings": warnings,
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

    # Only a still-pending source may be rejected — guard against rejecting one that was
    # already approved (would leave it ingested-but-marked-rejected on an approve/reject race).
    it = source_review_store.get(sid)
    if not it or it.get("status") != source_review_store.PENDING:
        raise HTTPException(status_code=404, detail="pending source not found")
    source_review_store.set_status(sid, source_review_store.REJECTED)
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

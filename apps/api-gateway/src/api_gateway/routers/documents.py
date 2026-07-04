"""Document upload → граф → viewer (§17.19 / §5.2.1 Document mode).

A researcher drops a PDF/DOCX/PPTX/XLSX into «Библиотека»; this router runs the
**real** ingestion pipeline in-process — :func:`ingestion_service.parsers.parse_document`
to parse pages/tables, then :class:`ingestion_service.pipeline.IngestionPipeline` to
extract entities/measurements/evidence and write them into the live graph store
(embedded Kuzu or server Neo4j, whichever ``get_store()`` returns). The freshly
ingested document's neighbourhood is returned as a :class:`GraphResponse` so the UI
can render the graph immediately (§23: «добавление документа обновляет граф»).

Parsed page text + tables are persisted as one JSON sidecar per document under
``runtime_dir/uploads/`` so the Document Viewer can page through the parsed content
(``/parsed``, ``/pages/{n}``) and offer a ``/reindex``. Writes are RBAC-gated to the
curator-and-up roles (same set as manual article add, §19).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from api_gateway import audit
from api_gateway.auth import current_role, current_user
from api_gateway.deps import get_store
from kg_common import GraphResponse, get_settings, make_id

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

# Same write-capable roles as manual article add (§19).
_CAN_UPLOAD = {"admin", "curator", "researcher", "analyst", "project_manager"}
_MAX_BYTES = 64 * 1024 * 1024  # 64 MB upload cap
_ALLOWED_SUFFIX = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md"}


def _uploads_dir() -> Path:
    d = Path(get_settings().runtime_dir) / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sidecar(doc_id: str) -> Path:
    # doc_id is "Document:<hash>". The read routes take {doc_id:path}, so a caller
    # could pass "../../secret" — collapse EVERY non-safe char (incl. "/" and ".")
    # so no directory separator survives, strip leading dots, then assert the
    # resolved path stays inside uploads/ (defence in depth against traversal).
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", doc_id).strip("_") or "doc"
    base = _uploads_dir().resolve()
    p = (base / f"{safe}.json").resolve()
    if p.parent != base:
        raise HTTPException(status_code=400, detail="invalid document id")
    return p


def _load_sidecar(doc_id: str) -> dict[str, Any]:
    p = _sidecar(doc_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="document not found")
    return json.loads(p.read_text(encoding="utf-8"))


def _require_upload(role: str) -> None:
    if role not in _CAN_UPLOAD:
        raise HTTPException(status_code=403, detail="role may not upload documents")


def _ingest_file(path: Path, *, use_llm: bool) -> dict[str, Any]:
    """Parse + ingest one file; return {doc_id, meta, stats}. Raises 422 if unparsable."""
    from ingestion_service.parsers import parse_document
    from ingestion_service.pipeline import IngestionPipeline

    parsed = parse_document(path)
    if parsed is None:
        raise HTTPException(status_code=422, detail="could not parse document")

    doc_id = make_id("Document", parsed.file_hash)
    # 3 LLM chunks/doc matches the ingestion CLI default (bounded cost per upload).
    pipe = IngestionPipeline(get_store(), use_llm=use_llm, llm_max_chunks=3)
    res = pipe.ingest(parsed)

    # Persist parsed content for the viewer (pages + tables + metadata).
    sidecar = {
        "doc_id": doc_id,
        "title": parsed.title,
        "doc_type": parsed.doc_type,
        "lang": parsed.lang,
        "country": parsed.country,
        "year": parsed.year,
        "file_hash": parsed.file_hash,
        "source_path": str(path),
        "page_count": len(parsed.pages),
        "status": res.get("status", "ok"),
        "chunks": res.get("chunks", 0),
        "extractor": "rule+llm" if use_llm else "rule",
        "pages": [{"page": p, "text": t} for p, t in parsed.pages],
        "tables": [{"page": t.page, "rows": t.rows} for t in parsed.tables],
    }
    _sidecar(doc_id).write_text(json.dumps(sidecar, ensure_ascii=False), encoding="utf-8")
    return {"doc_id": doc_id, "meta": sidecar, "stats": res}


def _doc_graph(doc_id: str) -> GraphResponse:
    """The ingested document's 2-hop neighbourhood as a §5.2.3 graph payload."""
    return get_store().neighbors(doc_id, depth=2, limit=300)


# -- request bodies --------------------------------------------------------
class ReindexBody(BaseModel):
    use_llm: bool = True


# -- endpoints -------------------------------------------------------------
@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    use_llm: bool = True,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """Accept a document, run ingestion, and return the resulting subgraph (§17.19)."""
    _require_upload(role)
    name = Path(file.filename or "document").name
    suffix = Path(name).suffix.lower()
    if suffix not in _ALLOWED_SUFFIX:
        raise HTTPException(status_code=415, detail=f"unsupported file type: {suffix or 'none'}")

    dest = _uploads_dir() / name
    size = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > _MAX_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="file too large (max 64 MB)")
            out.write(chunk)

    result = _ingest_file(dest, use_llm=use_llm)
    graph = _doc_graph(result["doc_id"])
    audit.record(
        "upload_document",
        user=user,
        role=role,
        detail={"doc_id": result["doc_id"], "status": result["stats"].get("status")},
    )
    return {
        "doc_id": result["doc_id"],
        "title": result["meta"]["title"],
        "status": result["stats"].get("status", "ok"),
        "page_count": result["meta"]["page_count"],
        "chunks": result["meta"]["chunks"],
        "graph": graph.model_dump(by_alias=True),
        "node_count": len(graph.nodes),
    }


@router.get("")
def list_documents(limit: int = 30) -> dict:
    """List recently uploaded documents (newest sidecars first)."""
    items: list[dict[str, Any]] = []
    # sidecars are named "<doc_id with ':'→'_'>.json"; make_id('Document', …) → "doc:…".
    files = sorted(_uploads_dir().glob("doc_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files[: max(1, min(limit, 200))]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        items.append(
            {
                "doc_id": d.get("doc_id"),
                "title": d.get("title"),
                "doc_type": d.get("doc_type"),
                "page_count": d.get("page_count"),
                "year": d.get("year"),
                "status": d.get("status"),
            }
        )
    return {"documents": items, "count": len(items)}


@router.get("/{doc_id:path}/parsed")
def document_parsed(doc_id: str) -> dict:
    """Full parsed content — pages + tables (§17.19 postраничный parsed-просмотр)."""
    d = _load_sidecar(doc_id)
    return {
        "doc_id": d["doc_id"],
        "title": d["title"],
        "page_count": d["page_count"],
        "pages": d["pages"],
        "tables": d["tables"],
    }


@router.get("/{doc_id:path}/pages/{page}")
def document_page(doc_id: str, page: int) -> dict:
    """One parsed page by 1-based number (§17.19)."""
    d = _load_sidecar(doc_id)
    for pg in d["pages"]:
        if pg["page"] == page:
            tables = [t for t in d["tables"] if t["page"] == page]
            return {"doc_id": d["doc_id"], "page": page, "text": pg["text"], "tables": tables}
    raise HTTPException(status_code=404, detail="page not found")


@router.get("/{doc_id:path}/graph", response_model=GraphResponse)
def document_graph(doc_id: str) -> GraphResponse:
    """The document's neighbourhood subgraph (§5.2.3)."""
    _load_sidecar(doc_id)  # 404 if unknown
    return _doc_graph(doc_id)


@router.post("/{doc_id:path}/reindex")
def reindex_document(
    doc_id: str,
    body: ReindexBody,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """Re-run ingestion for a previously uploaded document from its saved file (§17.19)."""
    _require_upload(role)
    d = _load_sidecar(doc_id)
    src = Path(d["source_path"])
    if not src.exists():
        raise HTTPException(status_code=410, detail="source file no longer available")
    result = _ingest_file(src, use_llm=body.use_llm)
    graph = _doc_graph(result["doc_id"])
    audit.record("reindex_document", user=user, role=role, detail={"doc_id": doc_id})
    return {
        "doc_id": result["doc_id"],
        "status": result["stats"].get("status", "ok"),
        "graph": graph.model_dump(by_alias=True),
        "node_count": len(graph.nodes),
    }


# -- corpus source listing + download -------------------------------------
# NB: these two routes MUST stay ABOVE the catch-all @router.get("/{doc_id:path}")
# below, or FastAPI folds "corpus" and ".../download" into the catch-all.
class CorpusSource(BaseModel):
    """A citable corpus item — a seed/manual :Paper or an uploaded :Document."""

    doc_id: str
    title: str
    doc_type: str
    year: int | None = None
    country: str | None = None
    practice_type: str | None = None
    evidence_strength: str | None = None
    domain: str | None = None
    url: str | None = None
    doi: str | None = None
    authors: list[str] = []
    has_parsed: bool = False


def _authors_list(node: dict[str, Any]) -> list[str]:
    """Authors as a list — native list, else split authors_text on '|' or ','."""
    val = node.get("authors")
    if isinstance(val, list):
        return [str(a).strip() for a in val if str(a).strip()]
    text = node.get("authors_text")
    if isinstance(text, str) and text.strip():
        return [a.strip() for a in re.split(r"[|,]", text) if a.strip()]
    return []


def _has_parsed(doc_id: str) -> bool:
    try:
        return _sidecar(doc_id).exists()
    except Exception:
        return False


def _as_int(v: Any) -> int | None:
    """Coerce a node property to int|None — dirty data (e.g. '2019 г.') becomes None
    instead of raising a pydantic ValidationError that would 500 the whole listing."""
    try:
        if v is None or v == "":
            return None
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


@router.get("/corpus")
def corpus_sources(
    limit: int = 200,
    q: str | None = None,
    doc_type: str | None = None,
) -> dict:
    """List citable corpus sources — seed/manual :Paper + uploaded :Document (§17.19)."""
    store = get_store()
    bounded = min(max(limit, 1), 500)
    # NB: LIMIT is interpolated as an int literal (not a bound $param) — the embedded
    # Kuzu store rejects a parameterized LIMIT, matching every other query in the repo
    # (graph.py, search.py). `bounded` is an int, so there is no injection surface.
    rows = store.rows(
        "MATCH (n:Node) WHERE n.label IN ['Paper','Document'] AND n.name IS NOT NULL "
        f"RETURN n LIMIT {int(bounded)}",
    )
    sources: list[CorpusSource] = []
    for r in rows:
        nd = store._node_dict(r[0])
        node_id = nd.get("id") or ""
        label = nd.get("label") or ""
        title = nd.get("name") or nd.get("canonical_name") or node_id
        sources.append(
            CorpusSource(
                doc_id=node_id,
                title=str(title),
                doc_type=str(label).lower(),
                year=_as_int(nd.get("year")),
                country=nd.get("country"),
                practice_type=nd.get("practice_type"),
                evidence_strength=nd.get("evidence_strength"),
                domain=nd.get("domain"),
                url=nd.get("url"),
                doi=nd.get("doi"),
                authors=_authors_list(nd),
                has_parsed=_has_parsed(node_id),
            )
        )
    if q:
        ql = q.lower()
        sources = [s for s in sources if ql in s.title.lower()]
    if doc_type:
        sources = [s for s in sources if s.doc_type == doc_type]
    sources.sort(key=lambda s: (0 if s.has_parsed else 1, s.title.lower()))
    return {"sources": [s.model_dump() for s in sources], "count": len(sources)}


@router.get("/{doc_id:path}/download")
def download_document(doc_id: str) -> Response:
    """Download a corpus item — parsed Markdown for uploads, else a citation card (§17.19)."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", doc_id).strip("_") or "doc"
    sidecar = _sidecar(doc_id)
    if sidecar.exists():
        d = json.loads(sidecar.read_text(encoding="utf-8"))
        title = d.get("title") or doc_id
        pages = d.get("pages") or []
        tables = d.get("tables") or []
        lines: list[str] = [f"# {title}", ""]
        lines.append(f"- doc_type: {d.get('doc_type') or ''}")
        lines.append(f"- year: {d.get('year') if d.get('year') is not None else ''}")
        lines.append(f"- pages: {d.get('page_count', len(pages))}")
        lines.append("")
        for pg in pages:
            lines.append(f"## Стр. {pg.get('page')}")
            lines.append("")
            lines.append(str(pg.get("text") or ""))
            lines.append("")
            for t in tables:
                if t.get("page") == pg.get("page"):
                    for row in t.get("rows") or []:
                        lines.append("| " + " | ".join(str(c) for c in row) + " |")
                    lines.append("")
        content = "\n".join(lines)
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{safe}.md"'},
        )

    node = get_store().get_node(doc_id)
    if node is not None:
        title = node.get("name") or node.get("canonical_name") or doc_id
        authors = _authors_list(node)
        lines = [f"Title: {title}"]
        if authors:
            lines.append("Authors: " + ", ".join(authors))
        if node.get("year") is not None:
            lines.append(f"Year: {node['year']}")
        if node.get("doi"):
            lines.append(f"DOI: {node['doi']}")
        if node.get("url"):
            lines.append(f"URL: {node['url']}")
        if node.get("country"):
            lines.append(f"Country: {node['country']}")
        if node.get("evidence_strength"):
            lines.append(f"Evidence strength: {node['evidence_strength']}")
        content = "\n".join(lines) + "\n"
        return Response(
            content=content,
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{safe}.txt"'},
        )

    raise HTTPException(status_code=404, detail="document not found")


@router.get("/{doc_id:path}")
def document_meta(doc_id: str) -> dict:
    """Document metadata — source, pages, parse status, extractor version (§17.19)."""
    d = _load_sidecar(doc_id)
    return {k: v for k, v in d.items() if k not in {"pages", "tables"}}

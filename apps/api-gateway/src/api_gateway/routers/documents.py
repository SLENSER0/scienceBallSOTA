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
from kg_common import GraphResponse, get_logger, get_settings, make_id

_log = get_logger("documents")
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

    # Push the just-written chunks into the search index (the graph write alone leaves the
    # doc invisible to search). Best-effort — never fails the upload.
    index = _index_doc_chunks(get_store(), doc_id)

    # A re-upload hits the idempotency guard (status 'skipped', chunks absent) — report the
    # REAL graph chunk count so it reads «уже в хранилище, N чанков», not a misleading 0.
    chunks = res.get("chunks", 0)
    if res.get("status") == "skipped":
        chunks = index.get("chunks", 0)

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
        "chunks": chunks,
        "extractor": "rule+llm" if use_llm else "rule",
        "pages": [{"page": p, "text": t} for p, t in parsed.pages],
        "tables": [{"page": t.page, "rows": t.rows} for t in parsed.tables],
    }
    _sidecar(doc_id).write_text(json.dumps(sidecar, ensure_ascii=False), encoding="utf-8")
    return {"doc_id": doc_id, "meta": sidecar, "stats": res, "index": index}


def _doc_graph(doc_id: str) -> GraphResponse:
    """The ingested document's 2-hop neighbourhood as a §5.2.3 graph payload."""
    return get_store().neighbors(doc_id, depth=2, limit=300)


def _index_doc_chunks(store: Any, doc_id: str) -> dict[str, Any]:
    """Push a freshly-ingested document's :Chunk nodes into the search index so it is
    actually SEARCHABLE — IngestionPipeline.ingest writes the graph only. Server profile
    only; each store is wrapped so a missing OpenSearch index degrades to Qdrant-only
    (never fails the upload). NB: we never call ensure_collection() — it wipes the live
    Qdrant collection — only upsert into the existing one."""
    if get_settings().runtime_profile != "server":
        return {"chunks": 0, "qdrant": None, "opensearch": None, "indexed": False}
    try:
        rows = store.rows(
            "MATCH (c:Node {label:'Chunk'}) WHERE c.doc_id=$id "
            "RETURN c.id, coalesce(c.text,''), c.doc_id, c.page",
            {"id": doc_id},
        )
    except Exception as exc:  # pragma: no cover - store defensiveness
        _log.warning("index.read_chunks_failed", doc_id=doc_id, error=str(exc)[:160])
        return {"chunks": 0, "qdrant": None, "opensearch": None, "indexed": False}
    buf = [
        {"id": r[0], "text": r[1], "doc_id": r[2], "page": r[3]}
        for r in rows
        if r[1] and str(r[1]).strip()
    ]
    out: dict[str, Any] = {"chunks": len(buf), "qdrant": None, "opensearch": None, "indexed": False}
    if not buf:
        return out
    try:
        from kg_retrievers.qdrant_server_store import QdrantServerStore

        qs = QdrantServerStore()
        qs.upsert_chunks(buf)  # NOT ensure_collection (destructive) — upsert into the live one
        out["qdrant"] = qs.count_by_doc(doc_id)
        out["indexed"] = bool(out["qdrant"])
    except Exception as exc:
        _log.warning("index.qdrant_failed", doc_id=doc_id, error=str(exc)[:160])
    try:
        from kg_retrievers.opensearch_store import OpenSearchKeywordStore

        osk = OpenSearchKeywordStore()
        osk.ensure_index()  # safe: creates only if missing
        osk.index_chunks(buf)
        out["opensearch"] = osk.count_by_doc(doc_id)
    except Exception as exc:
        _log.warning("index.opensearch_failed", doc_id=doc_id, error=str(exc)[:160])
    return out


def _doc_storage(store: Any, doc_id: str) -> dict[str, Any]:
    """Per-document storage confirmation: real graph node counts + search-index membership —
    the «landed in storage» proof the upload queue shows."""

    def _c(cypher: str) -> int:
        try:
            rows = list(store.rows(cypher, {"id": doc_id}))
            return int(rows[0][0]) if rows else 0
        except Exception:
            return 0

    graph = {
        "chunks": _c("MATCH (c:Node {label:'Chunk'}) WHERE c.doc_id=$id RETURN count(*)"),
        "measurements": _c(
            "MATCH (m:Node {label:'Measurement'}) WHERE m.doc_id=$id RETURN count(*)"
        ),
        "evidence": _c("MATCH (e:Node {label:'Evidence'}) WHERE e.doc_id=$id RETURN count(*)"),
    }
    graph["in_graph"] = graph["chunks"] > 0 or graph["measurements"] > 0
    qdrant: int | None = None
    opensearch: int | None = None
    if get_settings().runtime_profile == "server":
        try:
            from kg_retrievers.qdrant_server_store import QdrantServerStore

            qdrant = QdrantServerStore().count_by_doc(doc_id)
        except Exception:
            qdrant = None
        try:
            from kg_retrievers.opensearch_store import OpenSearchKeywordStore

            opensearch = OpenSearchKeywordStore().count_by_doc(doc_id)
        except Exception:
            opensearch = None
    return {
        "doc_id": doc_id,
        "graph": graph,
        "qdrant": qdrant,
        "opensearch": opensearch,
        "indexed": bool(qdrant),
    }


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
        "index": result.get("index", {}),
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
    """Full parsed content — sidecar pages/tables, else the document's graph :Chunk text."""
    p = _sidecar(doc_id)
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        return {
            "doc_id": d["doc_id"],
            "title": d["title"],
            "page_count": d["page_count"],
            "pages": d["pages"],
            "tables": d["tables"],
        }
    # Fallback: a corpus document's body lives in the graph as :Chunk nodes.
    store = get_store()
    chunks = _doc_chunks(store, doc_id)
    if chunks:
        node = store.get_node(doc_id) or {}
        title = node.get("name") or node.get("canonical_name") or doc_id
        return {
            "doc_id": doc_id,
            "title": str(title),
            "page_count": len(chunks),
            "pages": chunks,
            "tables": [],
        }
    raise HTTPException(status_code=404, detail="document not found")


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


@router.get("/{doc_id:path}/storage")
def document_storage(doc_id: str) -> dict:
    """«В хранилище?» — real per-document confirmation: graph node counts (chunks /
    measurements / evidence) + search-index membership (Qdrant / OpenSearch). The upload
    queue polls this so the user can SEE a document actually landed, not just a toast."""
    return _doc_storage(get_store(), doc_id)


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
    chunk_count: int = 0


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


def _doc_chunks(store: Any, doc_id: str, limit: int = 4000) -> list[dict[str, Any]]:
    """Real document body from the graph — :Chunk nodes for this doc, grouped by page.

    Uploaded docs keep parsed text in a sidecar; corpus documents (ingested into the
    graph) carry their body as :Chunk nodes (doc_id + page + text). This surfaces the
    actual text of a graph-only source for the viewer and download (§5.2)."""
    try:
        rows = store.rows(
            "MATCH (c:Node {label:'Chunk'}) WHERE c.doc_id = $id AND c.text IS NOT NULL "
            f"RETURN coalesce(c.page, 0) AS page, c.text AS text ORDER BY page LIMIT {int(limit)}",
            {"id": doc_id},
        )
    except Exception:
        return []
    by_page: dict[int, list[str]] = {}
    order: list[int] = []
    for page, text in rows:
        try:
            p = int(page)
        except (TypeError, ValueError):
            p = 0
        if p not in by_page:
            by_page[p] = []
            order.append(p)
        by_page[p].append(str(text or ""))
    return [{"page": p, "text": "\n\n".join(by_page[p])} for p in sorted(order)]


@router.get("/corpus")
def corpus_sources(
    limit: int = 200,
    q: str | None = None,
    doc_type: str | None = None,
) -> dict:
    """List citable corpus sources — seed/manual :Paper + uploaded :Document (§17.19)."""
    store = get_store()
    bounded = min(max(limit, 1), 500)
    label_map = {"paper": "Paper", "document": "Document"}
    dt = (doc_type or "").strip().lower()
    labels = [label_map[dt]] if dt in label_map else ["Paper", "Document"]
    labels_lit = "[" + ", ".join(f"'{lbl}'" for lbl in labels) + "]"

    # A plain "LIMIT n" over the whole corpus has no recency order, so once the seed corpus grows
    # past the cap a just-loaded source falls outside it and never shows (the reported «после
    # загрузки из дип-серч не показываются»). We rank user-added sources (deep-research/manual
    # :Paper + uploaded :Document) most-recent-first so they land in the kept set.
    #
    # This ranking is done in PYTHON, not Cypher: the default embedded store (Kuzu) has a FIXED
    # Node schema, so `source`/`ingested_at` live in the props JSON — referencing them in a
    # WHERE/ORDER BY raises a Kuzu Binder exception (Neo4j is schemaless and would allow it, but
    # both profiles must work). store._node_dict unpacks props, so we read them there. Candidates
    # are capped generously so a just-loaded source is never truncated at corpus scale.
    # NB: LIMIT + labels are literals (bounded int / fixed label names) — the embedded store
    # rejects a bound $param LIMIT, matching every other query in the repo. No injection surface.
    candidate_cap = 4000
    rows = store.rows(
        f"MATCH (n:Node) WHERE n.label IN {labels_lit} AND n.name IS NOT NULL "
        f"RETURN n LIMIT {candidate_cap}"
    )
    # Cheap pass (no CorpusSource / no _has_parsed I/O): rank user-added → most-recent → title,
    # then build only the kept top-`bounded`.
    cands: list[tuple[int, int, str, dict]] = []
    seen: set[str] = set()
    for r in rows:
        nd = store._node_dict(r[0])
        node_id = nd.get("id") or ""
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        src = str(nd.get("source") or "").lower()
        is_added = nd.get("label") == "Document" or src in ("deep-research", "manual")
        ia = _as_int(nd.get("ingested_at")) or 0
        title = str(nd.get("name") or nd.get("canonical_name") or node_id)
        cands.append((0 if is_added else 1, -ia, title.lower(), nd))
    cands.sort(key=lambda c: (c[0], c[1], c[2]))

    sources: list[CorpusSource] = []
    added_ids: set[str] = set()
    recency: dict[str, int] = {}
    for pri, neg_ia, _tl, nd in cands[:bounded]:
        node_id = nd.get("id") or ""
        if pri == 0:
            added_ids.add(node_id)
        if neg_ia:
            recency[node_id] = -neg_ia
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
    # Attach real-text counts (graph :Chunk per doc) in one bulk read so the UI knows
    # which sources have body text and can open/download the actual text.
    ids = [s.doc_id for s in sources]
    if ids:
        try:
            crows = store.rows(
                "MATCH (c:Node {label:'Chunk'}) WHERE c.doc_id IN $ids "
                "RETURN c.doc_id AS did, count(*) AS n",
                {"ids": ids},
            )
            counts = {str(did): int(n) for did, n in crows}
        except Exception:
            counts = {}
        for s in sources:
            s.chunk_count = counts.get(s.doc_id, 0)
    # User-added sources first, most-recently-loaded of those first, then real-text, then title
    # — so a just-loaded source lands at the very top of the showcase.
    sources.sort(
        key=lambda s: (
            0 if s.doc_id in added_ids else 1,
            -recency.get(s.doc_id, 0),
            0 if (s.has_parsed or s.chunk_count > 0) else 1,
            s.title.lower(),
        )
    )
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

    # Corpus document whose body lives in the graph → export the real :Chunk text.
    store = get_store()
    chunks = _doc_chunks(store, doc_id)
    if chunks:
        cnode = store.get_node(doc_id) or {}
        ctitle = cnode.get("name") or cnode.get("canonical_name") or doc_id
        clines = [f"# {ctitle}", ""]
        for pg in chunks:
            clines.append(f"## Стр. {pg['page']}")
            clines.append("")
            clines.append(pg["text"])
            clines.append("")
        return Response(
            content="\n".join(clines),
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

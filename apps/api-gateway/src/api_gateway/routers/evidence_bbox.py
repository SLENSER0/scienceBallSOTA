"""Bbox-подсветка текстового evidence на изображении страницы PDF (§14.9).

Text evidence in the graph carries a *locator* — ``doc_id`` + ``page`` + the cited
``text`` span (§3.6, :mod:`kg_common.evidence_locator`) — but no pixel geometry. So
the Evidence Inspector could only ever say «страница 7»: it could not point at the
*exact* rectangle on the scanned page that the citation came from. That is the last
mile of evidence-first — «клик по цитате → прыжок к точному прямоугольнику на скане».

This router closes that gap with **real** geometry, not a stub. Given an ``Evidence``
node it opens the document's already-persisted source PDF (the one the upload pipeline
saved under ``runtime_dir/uploads/``), and *locates the cited span on its page* with
:mod:`PyMuPDF` full-text search — trying the whole span first, then decreasing
word-windows, then the most distinctive single word, so long or lightly-reflowed spans
still resolve. The matched line-rectangles are returned as a bbox in PDF points, and
rendered as a highlighter overlay on the page pixmap.

Endpoints (all reader-role; restricted evidence is RBAC-gated exactly like
``/evidence/{id}``):

* ``GET /by-doc/{doc_id}``       — evidence spans on a document that carry a page+text,
  the inspector's pick-list.
* ``GET /locate/{evidence_id}``  — locate the span → ``{bbox, line_rects, page_size,
  match_quality, found}`` in PDF points (client can overlay it on any page render).
* ``GET /{evidence_id}/image``   — the page pixmap with the located span highlighted
  (cached PNG); ``pad`` optionally crops tight around the highlight.

Nothing here edits a hub file, the ingestion service, or any existing module: it reads
the persisted PDF and the graph, and only ever *reads*.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from api_gateway.auth import current_role
from api_gateway.deps import get_store
from kg_common import get_settings

router = APIRouter(prefix="/api/v1/evidence-bbox", tags=["evidence-bbox"])

# Roles allowed to read restricted evidence (mirrors evidence.py §5.2.6).
_PRIVILEGED = {"researcher", "analyst", "project_manager", "admin", "curator"}
_RESTRICTED = {"internal", "restricted", "commercial_secret"}

_MAX_SPAN_CHARS = 600  # cap the needle we search for (perf + PyMuPDF sanity)
_HL = (214, 118, 40)  # copper, matches the figures highlighter


# -- upload sidecar access (kept local, mirrors documents.py / figures.py) --
def _uploads_dir() -> Path:
    d = Path(get_settings().runtime_dir) / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_dir() -> Path:
    d = Path(get_settings().runtime_dir) / "evidence_bbox"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sidecar_path(doc_id: str) -> Path:
    return _uploads_dir() / f"{doc_id.replace(':', '_')}.json"


def _load_sidecar(doc_id: str) -> dict[str, Any]:
    p = _sidecar_path(doc_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="document not found (upload it first)")
    return json.loads(p.read_text(encoding="utf-8"))


def _source_pdf(doc_id: str) -> Path:
    sc = _load_sidecar(doc_id)
    src = Path(sc.get("source_path", ""))
    if src.suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail="bbox highlight supports PDF sources only")
    if not src.exists():
        raise HTTPException(status_code=410, detail="source PDF no longer available")
    return src


def _load_evidence(evidence_id: str, role: str) -> dict[str, Any]:
    nd = get_store().get_node(evidence_id)
    if nd is None or nd.get("label") != "Evidence":
        raise HTTPException(status_code=404, detail="evidence not found")
    if nd.get("confidentiality_level") in _RESTRICTED and role not in _PRIVILEGED:
        raise HTTPException(status_code=403, detail="restricted evidence — access denied")
    return nd


# -- span → PDF geometry (real, PyMuPDF full-text search) -------------------
def _import_fitz() -> Any:
    try:
        import fitz  # PyMuPDF

        return fitz
    except ImportError as exc:  # pragma: no cover - dependency is vendored
        raise HTTPException(status_code=503, detail="PyMuPDF not available") from exc


def _search(page: Any, needle: str) -> list[Any]:
    """``page.search_for`` with de-hyphenation when the flag is available."""
    fitz = _import_fitz()
    dehyph = getattr(fitz, "TEXT_DEHYPHENATE", 0)
    try:
        return list(page.search_for(needle, flags=dehyph) or [])
    except TypeError:  # older PyMuPDF without the flags kwarg
        return list(page.search_for(needle) or [])


def _locate_span(page: Any, span: str) -> tuple[list[Any], str]:
    """Find the cited span on a page → (line rectangles, match quality).

    Strategy, most-precise first, so long / lightly-reflowed spans still resolve:

    1. the whole normalised span (``exact``);
    2. non-overlapping word-windows of 8 → 5 → 3 words (``phrase``);
    3. the single most distinctive long word (``word``);
    4. nothing (``none``).
    """
    span = " ".join(span.split())[:_MAX_SPAN_CHARS]
    if not span:
        return [], "none"

    rects = _search(page, span)
    if rects:
        return rects, "exact"

    words = [w for w in span.split() if w]
    for win in (8, 5, 3):
        if len(words) < win:
            continue
        found: list[Any] = []
        for i in range(0, len(words) - win + 1, win):
            found.extend(_search(page, " ".join(words[i : i + win])))
        if found:
            return found, "phrase"

    # last resort — the longest, most distinctive token
    for word in sorted({w.strip(".,;:()[]«»\"'") for w in words}, key=len, reverse=True):
        if len(word) >= 5:
            found = _search(page, word)
            if found:
                return found, "word"
    return [], "none"


def _union(rects: list[Any]) -> list[float] | None:
    if not rects:
        return None
    x0 = min(float(r.x0) for r in rects)
    y0 = min(float(r.y0) for r in rects)
    x1 = max(float(r.x1) for r in rects)
    y1 = max(float(r.y1) for r in rects)
    return [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)]


def _locate(evidence: dict[str, Any]) -> dict[str, Any]:
    """Open the source PDF, locate the evidence span, return geometry in PDF points."""
    doc_id = str(evidence.get("doc_id", ""))
    span = (evidence.get("text") or "").strip()
    page_no = evidence.get("page")
    if not doc_id or page_no is None:
        raise HTTPException(status_code=422, detail="evidence has no doc_id/page locator")
    page_no = int(page_no)

    fitz = _import_fitz()
    doc = fitz.open(str(_source_pdf(doc_id)))
    try:
        if page_no < 1 or page_no > doc.page_count:
            raise HTTPException(status_code=404, detail="evidence page out of PDF range")
        page = doc[page_no - 1]
        pw, ph = float(page.rect.width), float(page.rect.height)
        rects, quality = _locate_span(page, span)
        line_rects = [
            [round(float(r.x0), 2), round(float(r.y0), 2), round(float(r.x1), 2), round(float(r.y1), 2)]  # noqa: E501
            for r in rects
        ]
    finally:
        doc.close()

    return {
        "doc_id": doc_id,
        "page": page_no,
        "page_width": round(pw, 2),
        "page_height": round(ph, 2),
        "bbox": _union(rects),
        "line_rects": line_rects,
        "match_quality": quality,
        "found": bool(rects),
        "span": span[:_MAX_SPAN_CHARS],
    }


# -- endpoints --------------------------------------------------------------
@router.get("/by-doc/{doc_id:path}")
def evidence_by_doc(
    doc_id: str,
    limit: int = Query(200, ge=1, le=500),
    role: str = Depends(current_role),
) -> dict:
    """Evidence spans on a document that carry a page + text (inspector pick-list)."""
    _load_sidecar(doc_id)  # 404 if the document is unknown
    rows = get_store().rows(
        "MATCH (e:Node {label:'Evidence', doc_id:$doc}) "
        "WHERE e.page IS NOT NULL AND e.text IS NOT NULL AND e.text <> '' "
        "RETURN e.id, e.page, e.text, e.confidence, e.evidence_strength, e.source_type "
        "ORDER BY e.page LIMIT $lim",
        {"doc": doc_id, "lim": int(limit)},
    )
    items = [
        {
            "evidence_id": r[0],
            "page": r[1],
            "text": r[2],
            "confidence": r[3],
            "evidence_strength": r[4],
            "source_type": r[5],
        }
        for r in rows
    ]
    return {"doc_id": doc_id, "evidence": items, "count": len(items)}


@router.get("/locate/{evidence_id:path}")
def locate_evidence(evidence_id: str, role: str = Depends(current_role)) -> dict:
    """Locate a cited span on its PDF page → bbox + per-line rects in PDF points (§14.9)."""
    evidence = _load_evidence(evidence_id, role)
    out = _locate(evidence)
    out["evidence_id"] = evidence_id
    return out


@router.get("/{evidence_id:path}/image")
def evidence_image(
    evidence_id: str,
    dpi: int = Query(150, ge=72, le=300),
    pad: int = Query(-1, ge=-1, le=400),
    role: str = Depends(current_role),
) -> Response:
    """Render the evidence's PDF page with the cited span highlighted (§14.9).

    ``pad >= 0`` crops tight around the highlight with that many points of padding;
    ``pad = -1`` (default) returns the whole page with the span highlighted in place.
    """
    evidence = _load_evidence(evidence_id, role)
    loc = _locate(evidence)

    cache = _cache_dir() / f"{evidence_id.replace(':', '_')}_{dpi}_{pad}.png"
    if cache.exists():
        return Response(content=cache.read_bytes(), media_type="image/png")

    fitz = _import_fitz()
    from PIL import Image, ImageDraw

    doc = fitz.open(str(_source_pdf(str(loc["doc_id"]))))
    try:
        page = doc[int(loc["page"]) - 1]
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        clip = None
        if pad >= 0 and loc["bbox"]:
            bx0, by0, bx1, by1 = loc["bbox"]
            clip = fitz.Rect(
                max(bx0 - pad, 0.0),
                max(by0 - pad, 0.0),
                min(bx1 + pad, float(page.rect.width)),
                min(by1 + pad, float(page.rect.height)),
            )
        pix = page.get_pixmap(matrix=mat, clip=clip)
        img_mode = "RGBA" if pix.alpha else "RGB"
        img = Image.frombytes(img_mode, (pix.width, pix.height), pix.samples).convert("RGB")
        draw = ImageDraw.Draw(img, "RGBA")
        ox, oy = (clip.x0, clip.y0) if clip is not None else (0.0, 0.0)
        for rx0, ry0, rx1, ry1 in loc["line_rects"]:
            rect = [(rx0 - ox) * zoom, (ry0 - oy) * zoom, (rx1 - ox) * zoom, (ry1 - oy) * zoom]
            draw.rectangle(rect, fill=(*_HL, 60), outline=(*_HL, 235), width=2)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        png = buf.getvalue()
    finally:
        doc.close()

    with contextlib.suppress(OSError):
        cache.write_bytes(png)
    return Response(content=png, media_type="image/png")

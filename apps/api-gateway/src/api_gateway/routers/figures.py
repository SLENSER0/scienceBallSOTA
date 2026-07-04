"""Figures as evidence — Figure nodes with PDF bbox in the graph + inspector (§23.34).

Docling/pdfplumber already give us page text and tables, but *figures* (charts,
micrographs, flowsheets, diagrams) never entered the graph — so a fact could never
point back at the actual picture that proves it. This router closes that gap with
**real** extraction, not a stub:

* ``POST /extract/{doc_id}`` opens the document's source PDF (the one the upload
  pipeline already saved under ``runtime_dir/uploads/``), locates every embedded
  raster figure with :mod:`PyMuPDF`, records its **page + bounding box + caption**,
  and upserts a ``:Figure`` node (label §8.1) linked ``(:Document)-[:HAS_FIGURE]->``.
  It then wires each figure to the facts it backs: any fact whose ``Evidence`` sits
  on the figure's page gets a ``(:fact)-[:SUPPORTED_BY {via:'figure'}]->(:Figure)``
  edge — image-evidence (§8.3, ``source_type=figure``).
* ``GET /{figure_id}/image`` renders the bytes on demand straight from the PDF —
  either the tight ``crop`` of the figure, or the whole page with the figure's bbox
  ``highlight``ed (the doctrine-of-evidence "here it is on the page" view for §17).
* ``GET /by-doc`` / ``GET /by-node`` feed the inspector list.

Read endpoints default to the reader role; extraction is curator-and-up (same write
set as document upload, §19). Nothing here edits a hub file or the ingestion service —
it reads the already-persisted PDF and writes only new ``:Figure`` nodes/edges.
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
from kg_common import get_settings, make_id

router = APIRouter(prefix="/api/v1/figures", tags=["figures"])

# Same write-capable roles as document upload / manual article add (§19).
_CAN_WRITE = {"admin", "curator", "researcher", "analyst", "project_manager"}

_MAX_FIGS = 40  # hard cap per document (keeps extraction bounded)
_MAX_PAGES = 60  # mirror the parser's page cap
_MIN_SIDE_PT = 48.0  # ignore hairlines / bullet glyphs smaller than this (points)
_MIN_AREA_FRAC = 0.012  # ignore images covering < 1.2 % of the page
_CHROME_PAGES = 3  # an identical bbox on ≥3 pages is a header/footer band, not a figure
_CAPTION_PREFIXES = (
    "рис", "рисунок", "fig", "figure", "табл", "table", "схема", "график", "диаграм",
)


# -- upload sidecar access (mirrors documents.py, kept local to avoid cross-imports) --
def _uploads_dir() -> Path:
    d = Path(get_settings().runtime_dir) / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _figures_dir() -> Path:
    d = Path(get_settings().runtime_dir) / "figures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sidecar_path(doc_id: str) -> Path:
    return _uploads_dir() / f"{doc_id.replace(':', '_')}.json"


def _load_sidecar(doc_id: str) -> dict[str, Any]:
    p = _sidecar_path(doc_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="document not found (upload it first)")
    return json.loads(p.read_text(encoding="utf-8"))


def _require_write(role: str) -> None:
    if role not in _CAN_WRITE:
        raise HTTPException(status_code=403, detail="role may not extract figures")


# -- figure extraction (real, PyMuPDF) --------------------------------------
def _caption_for(bbox: tuple[float, float, float, float], blocks: list[Any]) -> str:
    """Nearest caption-looking text block below (or overlapping) the figure bbox."""
    x0, _y0, x1, y1 = bbox
    best: tuple[float, str] | None = None
    for b in blocks:
        bx0, by0, bx1, text = b[0], b[1], b[2], (b[4] or "").strip()
        if not text:
            continue
        low = text.lstrip("0123456789.)( ").lower()
        looks_caption = low.startswith(_CAPTION_PREFIXES)
        # captions sit just under the image and overlap it horizontally
        below = by0 >= y1 - 8.0
        overlaps = min(x1, bx1) - max(x0, bx0) > 0
        if not (below and overlaps):
            continue
        gap = by0 - y1
        if gap > 90 and not looks_caption:
            continue
        score = gap - (1000.0 if looks_caption else 0.0)
        clean = " ".join(text.split())[:280]
        if best is None or score < best[0]:
            best = (score, clean)
    return best[1] if best else ""


def _extract_figures(pdf_path: Path) -> list[dict[str, Any]]:
    """Return per-figure dicts with page, bbox, page size, caption and pixel dims.

    Filters decorative chrome: hairlines, sub-1.2 %-of-page glyphs, and full-width
    header/footer bands that repeat on many pages.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - dependency is vendored
        raise HTTPException(status_code=503, detail="PyMuPDF not available") from exc

    doc = fitz.open(str(pdf_path))
    raw: list[dict[str, Any]] = []
    bbox_pages: dict[tuple[int, int, int, int], set[int]] = {}
    try:
        n_pages = min(doc.page_count, _MAX_PAGES)
        for pno in range(n_pages):
            page = doc[pno]
            pw, ph = float(page.rect.width), float(page.rect.height)
            page_area = max(pw * ph, 1.0)
            blocks = [b for b in page.get_text("blocks") if len(b) > 6 and b[6] == 0]
            # de-dup tiled images: keep the largest bbox per xref on this page
            per_xref: dict[int, dict[str, Any]] = {}
            for inf in page.get_image_info(xrefs=True):
                bb = inf.get("bbox")
                if not bb:
                    continue
                x0, y0, x1, y1 = (float(v) for v in bb)
                w, h = x1 - x0, y1 - y0
                if w < _MIN_SIDE_PT or h < _MIN_SIDE_PT:
                    continue
                if (w * h) / page_area < _MIN_AREA_FRAC:
                    continue
                # full-width decorative strip (header/footer rule, banner) → skip
                if w > 0.82 * pw and (h < 70.0 or w / max(h, 1.0) > 6.0):
                    continue
                xref = int(inf.get("xref", 0) or 0)
                cand = {
                    "page": pno + 1,
                    "bbox": (x0, y0, x1, y1),
                    "page_width": pw,
                    "page_height": ph,
                    "px_w": int(inf.get("width", 0) or 0),
                    "px_h": int(inf.get("height", 0) or 0),
                    "xref": xref,
                    "area": w * h,
                }
                prev = per_xref.get(xref)
                if prev is None or cand["area"] > prev["area"]:
                    per_xref[xref] = cand
            for cand in per_xref.values():
                x0, y0, x1, y1 = cand["bbox"]
                key = (round(x0), round(y0), round(x1), round(y1))
                bbox_pages.setdefault(key, set()).add(cand["page"])
                cand["_bbox_key"] = key
                cand["caption"] = _caption_for(cand["bbox"], blocks)
                raw.append(cand)
    finally:
        doc.close()

    # drop bboxes that repeat across many pages (page furniture)
    figs = [c for c in raw if len(bbox_pages.get(c["_bbox_key"], set())) < _CHROME_PAGES]
    # largest / most prominent first, capped
    figs.sort(key=lambda c: c["area"], reverse=True)
    return figs[:_MAX_FIGS]


# -- graph read helpers -----------------------------------------------------
def _figure_row_to_dict(r: list[Any]) -> dict[str, Any]:
    bbox_raw = r[3]
    try:
        bbox = json.loads(bbox_raw) if isinstance(bbox_raw, str) else (bbox_raw or [])
    except (TypeError, ValueError):
        bbox = []
    return {
        "figure_id": r[0],
        "doc_id": r[1],
        "page": r[2],
        "bbox": bbox,
        "page_width": r[4],
        "page_height": r[5],
        "caption": r[6] or "",
        "supported_facts": int(r[7] or 0),
    }


_FIG_COLS = (
    "f.id, f.doc_id, f.page, f.bbox, f.page_width, f.page_height, f.caption, "
    "size([(f)<-[:Rel {type:'SUPPORTED_BY'}]-(x) | x]) AS n"
)


# -- endpoints --------------------------------------------------------------
@router.post("/extract/{doc_id:path}")
def extract_figures(doc_id: str, role: str = Depends(current_role)) -> dict:
    """Extract figures from a document's source PDF into the graph (§23.34)."""
    _require_write(role)
    sc = _load_sidecar(doc_id)
    src = Path(sc.get("source_path", ""))
    if src.suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail="figure extraction supports PDF sources only")
    if not src.exists():
        raise HTTPException(status_code=410, detail="source PDF no longer available")

    figs = _extract_figures(src)
    store = get_store()
    out: list[dict[str, Any]] = []
    linked_total = 0
    for idx, fg in enumerate(figs):
        fig_id = make_id("Figure", f"{doc_id}|p{fg['page']}|{idx}")
        x0, y0, x1, y1 = fg["bbox"]
        caption = fg["caption"]
        store.upsert_node(
            fig_id,
            "Figure",
            name=caption or f"Рис. (стр. {fg['page']})",
            doc_id=doc_id,
            page=fg["page"],
            bbox=json.dumps([round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)]),
            page_width=round(fg["page_width"], 2),
            page_height=round(fg["page_height"], 2),
            px_width=fg["px_w"],
            px_height=fg["px_h"],
            caption=caption,
            source_type="figure",
            extractor="pymupdf-image-info",
        )
        store.upsert_edge(doc_id, fig_id, "HAS_FIGURE", extractor="pymupdf")
        # image-evidence: link facts whose Evidence lives on this figure's page
        fact_ids = store.rows(
            "MATCH (fact:Node)-[:Rel {type:'SUPPORTED_BY'}]->(e:Node {label:'Evidence'}) "
            "WHERE e.doc_id=$doc AND e.page=$page RETURN DISTINCT fact.id",
            {"doc": doc_id, "page": fg["page"]},
        )
        for (fid,) in ((row[0],) for row in fact_ids):
            store.upsert_edge(fid, fig_id, "SUPPORTED_BY", via="figure", source_type="figure")
            linked_total += 1
        out.append(
            {
                "figure_id": fig_id,
                "page": fg["page"],
                "bbox": [round(v, 2) for v in fg["bbox"]],
                "caption": caption,
                "supported_facts": len(fact_ids),
            }
        )
    return {
        "doc_id": doc_id,
        "figures": out,
        "count": len(out),
        "linked_facts": linked_total,
    }


@router.get("/by-doc/{doc_id:path}")
def figures_by_doc(doc_id: str, role: str = Depends(current_role)) -> dict:
    """List the Figure nodes extracted for a document (inspector source list)."""
    rows = get_store().rows(
        f"MATCH (f:Node {{label:'Figure', doc_id:$doc}}) RETURN {_FIG_COLS} ORDER BY f.page",
        {"doc": doc_id},
    )
    figs = [_figure_row_to_dict(r) for r in rows]
    return {"doc_id": doc_id, "figures": figs, "count": len(figs)}


@router.get("/by-node/{node_id:path}")
def figures_by_node(node_id: str, role: str = Depends(current_role)) -> dict:
    """Figures that back a fact node — the visual evidence for §17's inspector."""
    rows = get_store().rows(
        "MATCH (n:Node {id:$id})-[:Rel {type:'SUPPORTED_BY'}]->(f:Node {label:'Figure'}) "
        f"RETURN {_FIG_COLS}",
        {"id": node_id},
    )
    figs = [_figure_row_to_dict(r) for r in rows]
    return {"node_id": node_id, "figures": figs, "count": len(figs)}


@router.get("/{figure_id:path}/image")
def figure_image(
    figure_id: str,
    mode: str = Query("crop", pattern="^(crop|highlight)$"),
    dpi: int = Query(150, ge=72, le=300),
    role: str = Depends(current_role),
) -> Response:
    """Render figure bytes from the source PDF: tight ``crop`` or page ``highlight``."""
    store = get_store()
    node = store.get_node(figure_id)
    if not node or node.get("label") != "Figure":
        raise HTTPException(status_code=404, detail="figure not found")
    try:
        bbox = json.loads(node["bbox"]) if isinstance(node.get("bbox"), str) else node.get("bbox")
        x0, y0, x1, y1 = (float(v) for v in bbox)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="figure has no bbox") from exc

    doc_id = str(node.get("doc_id", ""))
    page_no = int(node.get("page", 1))
    cache = _figures_dir() / f"{figure_id.replace(':', '_')}_{mode}_{dpi}.png"
    if cache.exists():
        return Response(content=cache.read_bytes(), media_type="image/png")

    sc = _load_sidecar(doc_id)
    src = Path(sc.get("source_path", ""))
    if not src.exists():
        raise HTTPException(status_code=410, detail="source PDF no longer available")

    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(status_code=503, detail="PyMuPDF not available") from exc

    doc = fitz.open(str(src))
    try:
        if page_no < 1 or page_no > doc.page_count:
            raise HTTPException(status_code=404, detail="page out of range")
        page = doc[page_no - 1]
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        if mode == "crop":
            pix = page.get_pixmap(clip=fitz.Rect(x0, y0, x1, y1), matrix=mat)
            png = pix.tobytes("png")
        else:
            from PIL import Image, ImageDraw

            pix = page.get_pixmap(matrix=mat)
            img_mode = "RGBA" if pix.alpha else "RGB"
            img = Image.frombytes(img_mode, (pix.width, pix.height), pix.samples).convert("RGB")
            draw = ImageDraw.Draw(img, "RGBA")
            rect = [x0 * zoom, y0 * zoom, x1 * zoom, y1 * zoom]
            draw.rectangle(rect, fill=(214, 118, 40, 46), outline=(214, 118, 40, 255), width=4)
            buf = io.BytesIO()
            img.save(buf, "PNG")
            png = buf.getvalue()
    finally:
        doc.close()

    with contextlib.suppress(OSError):
        cache.write_bytes(png)
    return Response(content=png, media_type="image/png")

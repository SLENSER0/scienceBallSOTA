"""Figure-caption Evidence — caption→figure linkage + ``source_type=figure_caption`` (§5.7 / §8.3).

The figures pipeline (``routers/figures.py``, §23.34) already pulls figure *crops* out
of the source PDF into ``:Figure`` graph nodes with page + bbox + a best-effort caption
string. What it does **not** do is turn those captions into first-class **Evidence
anchors** — and §5.7 (line 1105/1108) + §8.3 (line 1341) require exactly that: every
figure caption must become an ``:Evidence`` node with ``source_type=figure_caption``,
carrying a real ``page`` and a real ``char_start``/``char_end`` span *into the parsed
page text*, wired back to the figure it describes. Those caption-Evidence nodes are what
let a fact cite the picture-with-words, and they feed the existing multimodal image
analysis (a captioned figure is now a citable, span-grounded source).

This router closes that gap with **real** work, not a stub:

* ``POST /build/{doc_id}`` — reuses the ``:Figure`` nodes already extracted by
  ``figures.py`` when present (no re-detection); if none exist yet it does its own
  bounded PyMuPDF figure+caption detection so the feature stands alone. For every
  figure that carries a caption it:
    - locates the caption inside the document's parsed page text (from the upload
      sidecar) to compute a **true** ``char_start``/``char_end`` span (§8.3), falling
      back to ``0..len`` only when the caption text can't be matched;
    - upserts an ``:Evidence`` node ``source_type=figure_caption`` (no
      ``extractor``/``model``/``confidence`` — those belong to the extraction stage,
      per §5.7);
    - wires the **caption→figure** link both ways:
      ``(:Figure)-[:HAS_CAPTION]->(:Evidence)`` and ``(:Evidence)-[:CAPTION_OF]->(:Figure)``.
* ``GET /by-doc/{doc_id}`` — caption-Evidence list for a document (inspector source).
* ``GET /by-figure/{figure_id}`` — the caption Evidence backing one figure.
* ``GET /{figure_id}/crop`` — renders the figure crop bytes from the source PDF, so the
  caption card can show the picture the caption describes.

Reads default to the reader role; ``build`` is curator-and-up (the document-write set,
§19). Nothing here edits a hub file or the ingestion service, and it never imports
``figures.py`` internals — it only reads persisted ``:Figure`` nodes / the saved PDF and
writes new ``:Evidence`` nodes + caption edges.
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from api_gateway.auth import current_role
from api_gateway.deps import get_store
from kg_common import get_settings, make_id, uuid5_id

router = APIRouter(prefix="/api/v1/figure-captions", tags=["figure-captions"])

# Same write-capable roles as document upload / figure extraction (§19).
_CAN_WRITE = {"admin", "curator", "researcher", "analyst", "project_manager"}

_MAX_FIGS = 40  # hard cap per document (bounded work)
_MAX_PAGES = 60  # mirror the parser's page cap
_MIN_SIDE_PT = 48.0  # ignore hairlines / bullet glyphs smaller than this (points)
_MIN_AREA_FRAC = 0.012  # ignore images covering < 1.2 % of the page
_CAPTION_PREFIXES = (
    "рис", "рисунок", "fig", "figure", "табл", "table", "схема", "график", "диаграм",
)


# -- upload sidecar + cache dirs (mirrors documents.py, kept local; no cross-imports) --
def _uploads_dir() -> Path:
    d = Path(get_settings().runtime_dir) / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _crops_dir() -> Path:
    d = Path(get_settings().runtime_dir) / "figure_caption_crops"
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
        raise HTTPException(status_code=403, detail="role may not build figure-caption evidence")


# -- caption span grounding --------------------------------------------------
def _page_text_map(sidecar: dict[str, Any]) -> dict[int, str]:
    out: dict[int, str] = {}
    for pg in sidecar.get("pages", []) or []:
        with contextlib.suppress(TypeError, ValueError):
            out[int(pg.get("page"))] = str(pg.get("text") or "")
    return out


def _norm_ws(s: str) -> str:
    return " ".join(s.split())


def _locate_span(page_text: str, caption: str) -> tuple[int, int]:
    """Char span of ``caption`` inside the parsed ``page_text`` (§8.3 char_start/char_end).

    Matching is whitespace-tolerant: docling's page text and PyMuPDF's block text
    collapse whitespace differently, so we search on a normalized copy and map the
    hit back to raw offsets. Falls back to ``(0, len(caption))`` when unmatched.
    """
    cap = _norm_ws(caption)
    if not cap or not page_text:
        return (0, len(caption))
    # Build normalized text with a map back to raw indices.
    norm_chars: list[str] = []
    raw_index: list[int] = []
    prev_space = False
    for i, ch in enumerate(page_text):
        if ch.isspace():
            if prev_space or not norm_chars:
                continue
            norm_chars.append(" ")
            raw_index.append(i)
            prev_space = True
        else:
            norm_chars.append(ch)
            raw_index.append(i)
            prev_space = False
    norm_text = "".join(norm_chars)
    # Try full caption, then a shrinking prefix (captions can get truncated at 280 ch).
    for probe_len in (len(cap), 60, 40, 24):
        probe = cap[:probe_len].strip()
        if len(probe) < 8:
            break
        pos = norm_text.find(probe)
        if pos >= 0:
            start = raw_index[pos]
            end_norm = min(pos + len(cap), len(raw_index) - 1)
            end = raw_index[end_norm] + 1
            return (start, max(end, start + len(probe)))
    return (0, len(caption))


# -- fallback figure+caption detection (real, PyMuPDF) ----------------------
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
    """Bounded per-figure dicts (page, bbox, page size, caption) — standalone fallback."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - dependency is vendored
        raise HTTPException(status_code=503, detail="PyMuPDF not available") from exc

    doc = fitz.open(str(pdf_path))
    raw: list[dict[str, Any]] = []
    try:
        n_pages = min(doc.page_count, _MAX_PAGES)
        for pno in range(n_pages):
            page = doc[pno]
            pw, ph = float(page.rect.width), float(page.rect.height)
            page_area = max(pw * ph, 1.0)
            blocks = [b for b in page.get_text("blocks") if len(b) > 6 and b[6] == 0]
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
                    "area": w * h,
                }
                prev = per_xref.get(xref)
                if prev is None or cand["area"] > prev["area"]:
                    per_xref[xref] = cand
            for cand in per_xref.values():
                cand["caption"] = _caption_for(cand["bbox"], blocks)
                raw.append(cand)
    finally:
        doc.close()
    raw.sort(key=lambda c: c["area"], reverse=True)
    return raw[:_MAX_FIGS]


# -- graph helpers ----------------------------------------------------------
def _existing_figures(doc_id: str) -> list[dict[str, Any]]:
    rows = get_store().rows(
        "MATCH (f:Node {label:'Figure', doc_id:$doc}) "
        "RETURN f.id, f.page, f.bbox, f.caption, f.page_width, f.page_height "
        "ORDER BY f.page",
        {"doc": doc_id},
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            bbox = json.loads(r[2]) if isinstance(r[2], str) else (r[2] or [])
        except (TypeError, ValueError):
            bbox = []
        out.append(
            {
                "figure_id": r[0],
                "page": int(r[1] or 0),
                "bbox": bbox,
                "caption": r[3] or "",
                "page_width": r[4],
                "page_height": r[5],
            }
        )
    return out


def _caption_evidence_rows(cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    rows = get_store().rows(cypher, params)
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            bbox = json.loads(r[7]) if isinstance(r[7], str) else (r[7] or [])
        except (TypeError, ValueError):
            bbox = []
        out.append(
            {
                "evidence_id": r[0],
                "figure_id": r[1],
                "doc_id": r[2],
                "page": int(r[3] or 0),
                "caption": r[4] or "",
                "char_start": int(r[5]) if r[5] is not None else None,
                "char_end": int(r[6]) if r[6] is not None else None,
                "bbox": bbox,
                "source_type": "figure_caption",
            }
        )
    return out


_EVID_COLS = (
    "e.id, f.id, e.doc_id, e.page, e.text, e.char_start, e.char_end, f.bbox"
)


# -- endpoints --------------------------------------------------------------
@router.post("/build/{doc_id:path}")
def build_caption_evidence(doc_id: str, role: str = Depends(current_role)) -> dict:
    """Turn a document's figure captions into ``figure_caption`` Evidence (§5.7/§8.3)."""
    _require_write(role)
    sidecar = _load_sidecar(doc_id)
    src = Path(sidecar.get("source_path", ""))
    page_text = _page_text_map(sidecar)
    store = get_store()

    # 1) reuse figures already extracted by figures.py; else detect ourselves.
    figures = _existing_figures(doc_id)
    self_extracted = False
    if not figures:
        if src.suffix.lower() != ".pdf":
            raise HTTPException(status_code=415, detail="caption evidence needs a PDF source")
        if not src.exists():
            raise HTTPException(status_code=410, detail="source PDF no longer available")
        raw = _extract_figures(src)
        self_extracted = True
        figures = [
            {
                "figure_id": make_id("Figure", f"{doc_id}|p{fg['page']}|{idx}"),
                "page": fg["page"],
                "bbox": list(fg["bbox"]),
                "caption": fg["caption"],
                "page_width": fg["page_width"],
                "page_height": fg["page_height"],
                "_raw": fg,
            }
            for idx, fg in enumerate(raw)
        ]

    now = datetime.now(UTC).isoformat()
    built: list[dict[str, Any]] = []
    captioned = 0
    for fg in figures:
        caption = (fg.get("caption") or "").strip()
        fig_id = fg["figure_id"]

        # When we detected figures ourselves, materialise the :Figure node (idempotent
        # with figures.py's id scheme so a later /figures/extract won't duplicate it).
        if self_extracted:
            bx = fg["bbox"]
            store.upsert_node(
                fig_id,
                "Figure",
                name=caption or f"Рис. (стр. {fg['page']})",
                doc_id=doc_id,
                page=fg["page"],
                bbox=json.dumps([round(float(v), 2) for v in bx]) if bx else "[]",
                page_width=round(float(fg["page_width"]), 2),
                page_height=round(float(fg["page_height"]), 2),
                px_width=fg["_raw"]["px_w"],
                px_height=fg["_raw"]["px_h"],
                caption=caption,
                source_type="figure",
                extractor="pymupdf-image-info",
            )
            store.upsert_edge(doc_id, fig_id, "HAS_FIGURE", extractor="pymupdf")

        if not caption:
            continue
        captioned += 1
        char_start, char_end = _locate_span(page_text.get(fg["page"], ""), caption)
        evid_id = uuid5_id("Evidence", doc_id, f"figure_caption|{fig_id}")
        # §8.3 figure_caption anchor: real span/location, no extractor/model/confidence yet.
        store.upsert_node(
            evid_id,
            "Evidence",
            text=caption,
            doc_id=doc_id,
            page=fg["page"],
            source_type="figure_caption",
            char_start=char_start,
            char_end=char_end,
            figure_id=fig_id,
            review_status="pending",
            created_at=now,
        )
        # caption <-> figure linkage (both directions).
        store.upsert_edge(fig_id, evid_id, "HAS_CAPTION", source_type="figure_caption")
        store.upsert_edge(evid_id, fig_id, "CAPTION_OF", source_type="figure_caption")
        built.append(
            {
                "evidence_id": evid_id,
                "figure_id": fig_id,
                "page": fg["page"],
                "caption": caption,
                "char_start": char_start,
                "char_end": char_end,
            }
        )

    return {
        "doc_id": doc_id,
        "figures_seen": len(figures),
        "captions_evidenced": captioned,
        "self_extracted": self_extracted,
        "evidence": built,
    }


@router.get("/by-doc/{doc_id:path}")
def caption_evidence_by_doc(doc_id: str, role: str = Depends(current_role)) -> dict:
    """List ``figure_caption`` Evidence anchors built for a document."""
    rows = _caption_evidence_rows(
        "MATCH (f:Node {label:'Figure', doc_id:$doc})-[:Rel {type:'HAS_CAPTION'}]->"
        "(e:Node {label:'Evidence'}) "
        f"RETURN {_EVID_COLS} ORDER BY e.page",
        {"doc": doc_id},
    )
    return {"doc_id": doc_id, "evidence": rows, "count": len(rows)}


@router.get("/by-figure/{figure_id:path}")
def caption_evidence_by_figure(figure_id: str, role: str = Depends(current_role)) -> dict:
    """The caption Evidence backing a single figure."""
    rows = _caption_evidence_rows(
        "MATCH (f:Node {id:$fid, label:'Figure'})-[:Rel {type:'HAS_CAPTION'}]->"
        "(e:Node {label:'Evidence'}) "
        f"RETURN {_EVID_COLS}",
        {"fid": figure_id},
    )
    return {"figure_id": figure_id, "evidence": rows, "count": len(rows)}


@router.get("/{figure_id:path}/crop")
def figure_crop(
    figure_id: str,
    dpi: int = Query(150, ge=72, le=300),
    role: str = Depends(current_role),
) -> Response:
    """Render the tight figure crop from the source PDF (the picture the caption describes)."""
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
    cache = _crops_dir() / f"{figure_id.replace(':', '_')}_{dpi}.png"
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
        pix = page.get_pixmap(clip=fitz.Rect(x0, y0, x1, y1), matrix=fitz.Matrix(zoom, zoom))
        png = pix.tobytes("png")
    finally:
        doc.close()

    with contextlib.suppress(OSError):
        cache.write_bytes(png)
    return Response(content=png, media_type="image/png")

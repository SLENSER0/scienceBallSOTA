"""OCR branch for scanned PDFs — API surface (§5.7 ``do_ocr`` / ``ocr_used``).

Scanned Russian metallurgical reports carry no text layer, so the default PDF
parser recovers nothing and the document silently drops out of the corpus — a
large blind spot. This router exposes the §5.7 OCR branch
(:mod:`ingestion_service.ocr_branch`) so an operator can:

* ``GET  /api/v1/ocr/engines`` — see which OCR backends are usable in this
  deployment (tesseract/pytesseract, PyMuPDF-native, EasyOCR), in priority order;
* ``POST /api/v1/ocr/analyze`` — upload a PDF and get the OCR-branch verdict:
  is it scanned, was OCR applied, how many characters were recovered, per-page
  accounting, and (optionally) the recovered text — with ``ocr_used`` recorded
  exactly as §5.7 requires;
* ``GET  /api/v1/ocr/corpus`` — survey the PDFs already uploaded into the runtime
  (``runtime_dir/uploads``), classifying each as text / recovered-by-OCR /
  scanned-blind-spot, so the size of the blind spot is quantified rather than
  guessed.

The heavy lifting (text probe, scanned-vs-text decision reused from
:func:`kg_extractors.ocr_decision.decide_ocr`, OCR pass) lives in the ingestion
module; this router is thin request/response glue only.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from api_gateway.auth import current_role
from kg_common import get_settings

router = APIRouter(prefix="/api/v1/ocr", tags=["ocr"])

# Same write-capable roles that may upload documents (§17.19).
_CAN_UPLOAD = {"admin", "curator", "researcher", "analyst", "project_manager"}
_MAX_BYTES = 512 * 1024 * 1024  # 512 MB, matching the document upload cap
_MAX_CORPUS_FILES = 200


def _require_upload(role: str) -> None:
    if role not in _CAN_UPLOAD:
        raise HTTPException(status_code=403, detail="role may not run OCR analysis")


def _uploads_dir() -> Path:
    return Path(get_settings().runtime_dir) / "uploads"


@router.get("/engines")
def ocr_engines() -> dict[str, Any]:
    """OCR backends usable in this deployment, in priority order (§5.7)."""
    from ingestion_service.ocr_branch import detect_ocr_engines

    engines = [e.as_dict() for e in detect_ocr_engines()]
    return {
        "engines": engines,
        "any_available": any(e["available"] for e in engines),
        "active": next((e["name"] for e in engines if e["available"]), None),
    }


@router.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    do_ocr: bool = Query(default=True),
    include_text: bool = Query(default=False),
    role: str = Depends(current_role),
) -> dict[str, Any]:
    """Run the §5.7 OCR branch on an uploaded PDF and return the full verdict.

    Detects whether the PDF is scanned (no text layer), applies OCR when an
    engine is available, and reports ``ocr_used`` plus per-page character
    recovery. ``include_text=true`` returns the recovered text per page.
    """
    _require_upload(role)
    name = Path(file.filename or "document.pdf").name
    if Path(name).suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail="OCR branch accepts PDF only")

    from ingestion_service.ocr_branch import run_ocr_branch

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        size = 0
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > _MAX_BYTES:
                raise HTTPException(status_code=413, detail="file too large (max 512 MB)")
            tmp.write(chunk)
        tmp.flush()
        try:
            result = run_ocr_branch(tmp.name, do_ocr=do_ocr)
        except Exception as exc:  # surface parse failures as 422
            raise HTTPException(status_code=422, detail=f"could not analyze PDF: {exc}") from exc

    payload = result.as_dict(include_text=include_text)
    payload["doc_name"] = name  # report the client-supplied name, not the tempfile
    return payload


@router.get("/corpus")
def corpus_survey(
    max_pages: int = Query(default=20, ge=1, le=60),
    do_ocr: bool = Query(default=True),
    limit: int = Query(default=_MAX_CORPUS_FILES, ge=1, le=_MAX_CORPUS_FILES),
) -> dict[str, Any]:
    """Classify every uploaded PDF as text / OCR-recovered / scanned blind spot (§5.7).

    Re-probes the PDFs saved under ``runtime_dir/uploads`` (bounded to ``max_pages``
    per document for responsiveness) and aggregates how much of the corpus is a
    scanned blind spot — the metric §5.7 exists to shrink.
    """
    from ingestion_service.ocr_branch import detect_ocr_engines, run_ocr_branch

    up = _uploads_dir()
    pdfs: list[Path] = []
    if up.exists():
        pdfs = sorted(up.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    pdfs = pdfs[:limit]

    engines = [e.as_dict() for e in detect_ocr_engines()]
    engine_available = any(e["available"] for e in engines)

    documents: list[dict[str, Any]] = []
    n_text = n_recovered = n_blind = 0
    recovered_chars_total = 0
    for pdf in pdfs:
        try:
            r = run_ocr_branch(pdf, do_ocr=do_ocr, max_pages=max_pages)
        except Exception:  # skip unreadable files, keep the survey going
            continue
        if not r.is_scanned:
            n_text += 1
            klass = "text"
        elif r.ocr_used:
            n_recovered += 1
            klass = "recovered"
        else:
            n_blind += 1
            klass = "blind_spot"
        recovered_chars_total += r.recovered_chars
        documents.append(
            {
                "doc_name": r.doc_name,
                "class": klass,
                "is_scanned": r.is_scanned,
                "ocr_used": r.ocr_used,
                "engine": r.engine,
                "page_count": r.page_count,
                "empty_page_fraction": round(r.decision.empty_page_fraction, 3),
                "recovered_chars": r.recovered_chars,
            }
        )

    scanned = n_recovered + n_blind
    return {
        "engine_available": engine_available,
        "engines": engines,
        "totals": {
            "documents": len(documents),
            "text": n_text,
            "scanned": scanned,
            "recovered": n_recovered,
            "blind_spot": n_blind,
            "recovered_chars": recovered_chars_total,
            "recovery_rate": round(n_recovered / scanned, 3) if scanned else None,
        },
        "documents": documents,
    }

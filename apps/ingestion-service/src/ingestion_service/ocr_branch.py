"""OCR branch for scanned PDFs (§5.7 ``do_ocr`` / ``ocr_used``).

The default PDF parser (:mod:`ingestion_service.parsers`) reads the *text layer*
of a PDF with ``pdfplumber``/``pypdf``. A **scanned** document — a photographed
or image-only PDF, exactly the shape of the Russian metallurgical reports in this
corpus — carries no text layer, so those parsers return (almost) nothing and the
document silently drops out of ingestion: a large blind spot. §5.7 requires an
OCR branch that (a) *detects* a scanned PDF, (b) runs OCR to recover the glyphs,
and (c) records the ``ocr_used`` flag in the document's parse metadata.

This module implements that branch as pure orchestration on top of two pieces
that already exist elsewhere, reused rather than re-implemented:

* the OCR-need heuristic :func:`kg_extractors.ocr_decision.decide_ocr` — decides
  from per-page character yield whether a PDF is image-heavy (нужен OCR);
* the parse-manifest ``ocr_used`` field (:mod:`ingestion_service.parse_manifest`)
  — the metadata slot this branch fills.

Text probing prefers PyMuPDF (``fitz``) because it recovers a hidden/searchable
text layer that ``pdfplumber`` frequently misses (many "scanned" reports are in
fact searchable PDFs — recovering that layer is a real win with zero OCR cost),
falling back to ``pdfplumber``/``pypdf``. When a page genuinely has no text and
an OCR engine is installed, the page is rasterised and OCR'd; engines are probed
at runtime and used in priority order, so the branch degrades gracefully to a
clear "scanned, needs OCR, no engine available" verdict when none is present.

Pure orchestration — no network, no writes; callers persist the result.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kg_common import get_logger
from kg_extractors.ocr_decision import OcrDecision, decide_ocr

_log = get_logger("ocr_branch")

#: Per-page threshold below which a page counts as "no text layer" (§5.7).
DEFAULT_MIN_CHARS = 100
#: Empty-page fraction at/above which the document is judged scanned (§5.7).
DEFAULT_EMPTY_FRAC = 0.5
#: Hard cap on pages processed per document (matches the parser's own cap).
DEFAULT_MAX_PAGES = 60
#: Rasterisation resolution for the OCR pass (dots per inch).
_OCR_DPI = 220
#: Tesseract language pack — Russian + English for the metallurgical corpus.
_OCR_LANG = "rus+eng"
#: Minimum OCR-recovered chars for a page to count as genuinely recovered.
_MIN_RECOVERED_CHARS = 8


@dataclass(frozen=True)
class OcrEngine:
    """One OCR backend and whether it is usable in this deployment."""

    name: str
    available: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "available": self.available, "detail": self.detail}


@dataclass(frozen=True)
class OcrPage:
    """Per-page accounting for the OCR branch (§5.7)."""

    page: int
    pre_chars: int  # characters from the text layer before OCR
    post_chars: int  # characters after OCR (== pre_chars when OCR not applied)
    ocr_applied: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "pre_chars": self.pre_chars,
            "post_chars": self.post_chars,
            "ocr_applied": self.ocr_applied,
            "recovered_chars": max(0, self.post_chars - self.pre_chars),
        }


@dataclass(frozen=True)
class OcrBranchResult:
    """Outcome of the §5.7 OCR branch for one PDF."""

    doc_name: str
    is_scanned: bool  # decide_ocr verdict — image-heavy document
    ocr_used: bool  # OCR was actually applied and recovered text
    engine: str  # engine used, or "none"
    decision: OcrDecision
    page_count: int
    pages: list[OcrPage]
    pre_chars_total: int
    post_chars_total: int
    text_by_page: dict[int, str]

    @property
    def recovered_chars(self) -> int:
        """Characters gained by OCR over the bare text layer."""
        return max(0, self.post_chars_total - self.pre_chars_total)

    @property
    def blind_spot(self) -> bool:
        """Scanned but *not* recovered — a document still lost to the graph."""
        return self.is_scanned and not self.ocr_used

    def as_dict(self, *, include_text: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "doc_name": self.doc_name,
            "is_scanned": self.is_scanned,
            "ocr_used": self.ocr_used,
            "engine": self.engine,
            "decision": self.decision.as_dict(),
            "page_count": self.page_count,
            "pre_chars_total": self.pre_chars_total,
            "post_chars_total": self.post_chars_total,
            "recovered_chars": self.recovered_chars,
            "blind_spot": self.blind_spot,
            "pages": [p.as_dict() for p in self.pages],
        }
        if include_text:
            out["text_by_page"] = dict(self.text_by_page)
        return out


# --------------------------------------------------------------------------- #
# Engine detection
# --------------------------------------------------------------------------- #
def _tesseract_binary() -> str | None:
    """Absolute path of the ``tesseract`` binary, or ``None`` when absent."""
    import shutil

    return shutil.which("tesseract")


def detect_ocr_engines() -> list[OcrEngine]:
    """Probe which OCR backends are usable here, in priority order (§5.7)."""
    engines: list[OcrEngine] = []
    tess = _tesseract_binary()

    # 1) pytesseract (Python wrapper around the tesseract binary + Pillow).
    try:
        import pytesseract  # noqa: F401  (probe only)

        have_pil = _have("PIL")
        have_fitz = _have("fitz")
        ok = bool(tess) and have_pil and have_fitz
        detail = (
            "ready"
            if ok
            else "needs: "
            + ", ".join(
                x
                for x, present in (
                    ("tesseract binary", bool(tess)),
                    ("Pillow", have_pil),
                    ("PyMuPDF", have_fitz),
                )
                if not present
            )
        )
        engines.append(OcrEngine("pytesseract", ok, detail))
    except ImportError:
        engines.append(OcrEngine("pytesseract", False, "python package not installed"))

    # 2) PyMuPDF native OCR textpage (uses the tesseract binary directly).
    if _have("fitz"):
        ok = bool(tess)
        engines.append(
            OcrEngine(
                "pymupdf_ocr",
                ok,
                "ready" if ok else "needs: tesseract binary",
            )
        )
    else:
        engines.append(OcrEngine("pymupdf_ocr", False, "PyMuPDF not installed"))

    # 3) EasyOCR (self-contained deep model — no external binary).
    engines.append(
        OcrEngine(
            "easyocr",
            _have("easyocr"),
            "ready" if _have("easyocr") else "python package not installed",
        )
    )
    return engines


def _have(module: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(module) is not None


def _first_available(engines: list[OcrEngine]) -> str | None:
    for e in engines:
        if e.available:
            return e.name
    return None


# --------------------------------------------------------------------------- #
# Text-layer probe
# --------------------------------------------------------------------------- #
def probe_text_layer(path: Path, *, max_pages: int = DEFAULT_MAX_PAGES) -> dict[int, str]:
    """Extract the existing text layer per page (1-based), preferring PyMuPDF.

    PyMuPDF recovers hidden/searchable text that ``pdfplumber`` often misses, so
    it is tried first; ``pdfplumber`` then ``pypdf`` are the fallbacks. Pages
    with no text still appear (empty string) so page numbering stays intact.
    """
    if _have("fitz"):
        try:
            return _probe_fitz(path, max_pages)
        except Exception as exc:  # pragma: no cover - defensive
            _log.warning("ocr_branch.fitz_probe_failed", error=str(exc)[:150])
    return _probe_pdfplumber(path, max_pages)


def _probe_fitz(path: Path, max_pages: int) -> dict[int, str]:
    import fitz  # PyMuPDF

    out: dict[int, str] = {}
    with fitz.open(str(path)) as doc:
        for i, page in enumerate(doc, start=1):
            if i > max_pages:
                break
            out[i] = page.get_text("text") or ""
    return out


def _probe_pdfplumber(path: Path, max_pages: int) -> dict[int, str]:
    out: dict[int, str] = {}
    try:
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                if i > max_pages:
                    break
                out[i] = page.extract_text() or ""
        return out
    except Exception:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        for i, page in enumerate(reader.pages[:max_pages], start=1):
            out[i] = page.extract_text() or ""
        return out


# --------------------------------------------------------------------------- #
# OCR pass
# --------------------------------------------------------------------------- #
def _ocr_page(path: Path, page_index0: int, engine: str) -> str:
    """OCR a single page (0-based index) with the chosen engine; '' on failure."""
    try:
        if engine == "pytesseract":
            return _ocr_pytesseract(path, page_index0)
        if engine == "pymupdf_ocr":
            return _ocr_pymupdf(path, page_index0)
        if engine == "easyocr":
            return _ocr_easyocr(path, page_index0)
    except Exception as exc:  # pragma: no cover - engine-specific runtime issues
        _log.warning(
            "ocr_branch.page_ocr_failed",
            engine=engine,
            page=page_index0 + 1,
            error=str(exc)[:150],
        )
    return ""


def _render_png(path: Path, page_index0: int) -> bytes:
    import fitz

    with fitz.open(str(path)) as doc:
        page = doc[page_index0]
        pix = page.get_pixmap(dpi=_OCR_DPI)
        return pix.tobytes("png")


def _ocr_pytesseract(path: Path, page_index0: int) -> str:
    import pytesseract
    from PIL import Image

    img = Image.open(io.BytesIO(_render_png(path, page_index0)))
    return pytesseract.image_to_string(img, lang=_OCR_LANG) or ""


def _ocr_pymupdf(path: Path, page_index0: int) -> str:
    import fitz

    with fitz.open(str(path)) as doc:
        page = doc[page_index0]
        tp = page.get_textpage_ocr(flags=0, language=_OCR_LANG, dpi=_OCR_DPI, full=True)
        return page.get_text("text", textpage=tp) or ""


_EASYOCR_READER: Any = None


def _ocr_easyocr(path: Path, page_index0: int) -> str:
    import easyocr

    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        _EASYOCR_READER = easyocr.Reader(["ru", "en"], gpu=False)
    lines = _EASYOCR_READER.readtext(_render_png(path, page_index0), detail=0, paragraph=True)
    return "\n".join(str(x) for x in lines)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_ocr_branch(
    path: str | Path,
    *,
    do_ocr: bool = True,
    min_chars: int = DEFAULT_MIN_CHARS,
    empty_frac: float = DEFAULT_EMPTY_FRAC,
    max_pages: int = DEFAULT_MAX_PAGES,
    engine: str | None = None,
) -> OcrBranchResult:
    """Run the §5.7 OCR branch for one PDF and return a full accounting.

    1. Probe the text layer per page (PyMuPDF preferred).
    2. Decide whether the document is scanned via :func:`decide_ocr`.
    3. When scanned, ``do_ocr`` is set, and an engine is available, OCR each
       empty page and merge the recovered glyphs; ``ocr_used`` is ``True`` iff
       at least one page was recovered.

    ``engine`` forces a specific backend; otherwise the first available engine
    (priority order of :func:`detect_ocr_engines`) is used. No engine → the
    verdict is still returned with ``ocr_used=False`` (an honest blind spot).
    """
    p = Path(path)
    text_by_page = probe_text_layer(p, max_pages=max_pages)
    page_nums = sorted(text_by_page)
    pre_counts = [len(text_by_page[n].strip()) for n in page_nums]

    decision = decide_ocr(pre_counts, min_chars=min_chars, empty_frac_threshold=empty_frac)

    chosen = engine
    if chosen is None and do_ocr and decision.needs_ocr:
        chosen = _first_available(detect_ocr_engines())

    pages: list[OcrPage] = []
    ocr_used = False
    for n in page_nums:
        pre = len(text_by_page[n].strip())
        applied = False
        post = pre
        if do_ocr and decision.needs_ocr and chosen and pre < min_chars:
            recovered = _ocr_page(p, n - 1, chosen).strip()
            if len(recovered) >= _MIN_RECOVERED_CHARS and len(recovered) > pre:
                text_by_page[n] = recovered
                post = len(recovered)
                applied = True
                ocr_used = True
        pages.append(OcrPage(page=n, pre_chars=pre, post_chars=post, ocr_applied=applied))

    return OcrBranchResult(
        doc_name=p.name,
        is_scanned=decision.needs_ocr,
        ocr_used=ocr_used,
        engine=chosen if ocr_used else "none",
        decision=decision,
        page_count=len(page_nums),
        pages=pages,
        pre_chars_total=sum(pr.pre_chars for pr in pages),
        post_chars_total=sum(pr.post_chars for pr in pages),
        text_by_page=text_by_page,
    )

"""Document format detection by magic bytes + filename tiebreak (§5.3).

Ingestion (§5) needs to know *what* a byte blob is before dispatching it to the
right loader (PDF text-layer, OOXML unzip, HTML strip, plain-text passthrough).
This module answers that with :func:`detect_format`, which inspects the leading
*magic bytes* and, where those are ambiguous, falls back to the filename
extension:

* ``%PDF`` → PDF (определяется по сигнатуре);
* ``PK\\x03\\x04`` (ZIP) → an OOXML office file — ``docx`` / ``pptx`` / ``xlsx``
  distinguished by the inner archive layout (``word/`` vs ``ppt/`` vs ``xl/``)
  or, when the archive is unreadable/truncated, by the filename extension
  (внутренние имена или расширение);
* ``<!doctype html`` / ``<html`` → HTML (разметка);
* otherwise, printable/decodable bytes → plain text (текст по умолчанию), and
  an empty blob is treated as text.

The result is a frozen :class:`FormatInfo` (``mime`` / ``ext`` / ``kind``).
:func:`is_supported` reports whether a loader exists for it, and
:func:`ensure_supported` raises :class:`UnsupportedFormatError` when one does
not. Pure Python — no I/O, no third-party dependencies.
"""

from __future__ import annotations

import io
import os
import zipfile
from dataclasses import dataclass

# --- kind tokens (виды документов), §5.3 -------------------------------------
KIND_PDF = "pdf"
KIND_DOCX = "docx"
KIND_PPTX = "pptx"
KIND_XLSX = "xlsx"
KIND_HTML = "html"
KIND_TEXT = "text"
KIND_ZIP = "zip"  # a ZIP we could not classify as OOXML (не распознанный архив)
KIND_UNKNOWN = "unknown"  # binary blob of unknown type (неизвестный бинарь)

#: ``kind`` → ``(mime, canonical_ext)``. The single source of truth (§5.3).
_REGISTRY: dict[str, tuple[str, str]] = {
    KIND_PDF: ("application/pdf", "pdf"),
    KIND_DOCX: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx",
    ),
    KIND_PPTX: (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "pptx",
    ),
    KIND_XLSX: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ),
    KIND_HTML: ("text/html", "html"),
    KIND_TEXT: ("text/plain", "txt"),
    KIND_ZIP: ("application/zip", "zip"),
    KIND_UNKNOWN: ("application/octet-stream", ""),
}

#: Kinds an ingestion loader (§5) actually knows how to read.
SUPPORTED_KINDS: frozenset[str] = frozenset(
    {KIND_PDF, KIND_DOCX, KIND_PPTX, KIND_XLSX, KIND_HTML, KIND_TEXT}
)

# ZIP local-file / empty-archive / spanned signatures (сигнатуры ZIP).
_ZIP_SIGS: tuple[bytes, ...] = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_UTF8_BOM = b"\xef\xbb\xbf"

#: Filename extension → kind, used as a tiebreak when magic bytes are ambiguous.
_EXT_TO_KIND: dict[str, str] = {
    "pdf": KIND_PDF,
    "docx": KIND_DOCX,
    "pptx": KIND_PPTX,
    "xlsx": KIND_XLSX,
    "html": KIND_HTML,
    "htm": KIND_HTML,
    "txt": KIND_TEXT,
    "text": KIND_TEXT,
    "md": KIND_TEXT,
}

#: OOXML archive marker directory → kind (внутренняя раскладка OOXML).
_OOXML_DIRS: tuple[tuple[str, str], ...] = (
    ("word/", KIND_DOCX),
    ("ppt/", KIND_PPTX),
    ("xl/", KIND_XLSX),
)


class UnsupportedFormatError(Exception):
    """Raised when a detected format has no ingestion loader (§5.3).

    Carries the offending :class:`FormatInfo` on :attr:`fmt` for the caller.
    """

    def __init__(self, fmt: FormatInfo) -> None:
        self.fmt = fmt
        super().__init__(f"unsupported document format: kind={fmt.kind!r} mime={fmt.mime!r}")


@dataclass(frozen=True)
class FormatInfo:
    """Detected document format (§5.3).

    Fields
    ------
    mime
        IANA media type, e.g. ``"application/pdf"`` (MIME-тип).
    ext
        Canonical lowercase extension without a dot, e.g. ``"pdf"``; may be
        empty for a truly unknown blob (каноническое расширение).
    kind
        Normalized kind token — one of the ``KIND_*`` constants (вид).
    """

    mime: str
    ext: str
    kind: str

    def as_dict(self) -> dict[str, object]:
        """Full structured view (все поля)."""
        return {"mime": self.mime, "ext": self.ext, "kind": self.kind}


def _ext_of(filename: str | None) -> str:
    """Lowercase extension of *filename* without the dot (``""`` if none)."""
    if not filename:
        return ""
    _, dot_ext = os.path.splitext(filename)
    return dot_ext[1:].lower() if dot_ext.startswith(".") else ""


def _info(kind: str, *, ext: str | None = None) -> FormatInfo:
    """Build a :class:`FormatInfo` from the registry, overriding *ext* if given."""
    mime, default_ext = _REGISTRY[kind]
    return FormatInfo(mime=mime, ext=ext if ext is not None else default_ext, kind=kind)


def _classify_zip(body: bytes, ext: str) -> str:
    """Classify a ZIP blob as an OOXML kind by inner names, else by *ext*, else ZIP."""
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            names = archive.namelist()
    except (zipfile.BadZipFile, OSError):
        names = []  # truncated/partial archive → fall back to the extension
    for prefix, kind in _OOXML_DIRS:
        if any(name.startswith(prefix) for name in names):
            return kind
    ext_kind = _EXT_TO_KIND.get(ext)
    if ext_kind in {KIND_DOCX, KIND_PPTX, KIND_XLSX}:
        return ext_kind
    return KIND_ZIP


def _is_html(body: bytes) -> bool:
    """True if *body* opens with an HTML doctype or ``<html>`` tag (после пробелов)."""
    head = body[:512].lstrip()[:64].lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def _looks_text(body: bytes) -> bool:
    """True if *body* is plausibly text: no NUL and UTF-8/printable (правдоподобный текст)."""
    sample = body[:8192]
    if b"\x00" in sample:
        return False  # a NUL byte is a strong binary signal (признак бинаря)
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        # Non-UTF-8: accept if almost all bytes are printable/whitespace (latin-1-ish).
        printable = sum(1 for byte in sample if byte in _PRINTABLE_BYTES)
        return bool(sample) and printable / len(sample) >= 0.9


# Tab, LF, CR, FF, ESC plus every byte from space (0x20) upward (печатные байты).
_PRINTABLE_BYTES: frozenset[int] = frozenset({0x09, 0x0A, 0x0C, 0x0D, 0x1B}) | frozenset(
    range(0x20, 0x100)
)


def detect_format(data: bytes, filename: str | None = None) -> FormatInfo:
    """Detect the format of *data*, using *filename*'s extension as a tiebreak (§5.3).

    Never raises for unrecognized input — returns a best-effort :class:`FormatInfo`
    (whose ``kind`` may be unsupported). Use :func:`ensure_supported` to enforce.

    Detection order (порядок): empty → text; ``%PDF`` → pdf; ZIP → OOXML by inner
    layout or extension; HTML markup → html; printable bytes → text; else unknown.
    """
    ext = _ext_of(filename)
    body = data[len(_UTF8_BOM) :] if data.startswith(_UTF8_BOM) else data

    if not body:  # empty blob (or bare BOM) is treated as text (пустое → текст)
        return _info(KIND_TEXT)
    if body.startswith(b"%PDF"):
        return _info(KIND_PDF)
    if body.startswith(_ZIP_SIGS):
        return _info(_classify_zip(body, ext))
    if _is_html(body):
        return _info(KIND_HTML)
    if _looks_text(body):
        # Extension tiebreak: a text-looking .html/.htm still reads as HTML.
        if _EXT_TO_KIND.get(ext) == KIND_HTML:
            return _info(KIND_HTML)
        return _info(KIND_TEXT)
    return _info(KIND_UNKNOWN, ext=ext)


def is_supported(fmt: FormatInfo) -> bool:
    """True if an ingestion loader exists for *fmt* (§5.3)."""
    return fmt.kind in SUPPORTED_KINDS


def ensure_supported(fmt: FormatInfo) -> FormatInfo:
    """Return *fmt* unchanged, or raise :class:`UnsupportedFormatError` if unsupported."""
    if not is_supported(fmt):
        raise UnsupportedFormatError(fmt)
    return fmt

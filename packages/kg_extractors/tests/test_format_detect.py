"""Document format detection by magic bytes + filename tiebreak (§5.3)."""

from __future__ import annotations

import io
import zipfile
from dataclasses import FrozenInstanceError

import pytest

from kg_extractors.format_detect import (
    KIND_DOCX,
    KIND_HTML,
    KIND_PDF,
    KIND_PPTX,
    KIND_TEXT,
    KIND_UNKNOWN,
    KIND_XLSX,
    KIND_ZIP,
    FormatInfo,
    UnsupportedFormatError,
    detect_format,
    ensure_supported,
    is_supported,
)


def _ooxml(marker_dir: str, doc_name: str) -> bytes:
    """Build a minimal valid OOXML ZIP with a ``marker_dir/doc_name`` entry."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(f"{marker_dir}/{doc_name}", "<xml/>")
    return buf.getvalue()


def test_pdf_magic() -> None:
    fmt = detect_format(b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n")
    assert fmt.kind == KIND_PDF
    assert fmt.mime == "application/pdf"
    assert fmt.ext == "pdf"
    assert is_supported(fmt)


def test_docx_by_inner_name() -> None:
    # No filename at all — detection must come purely from the archive layout.
    fmt = detect_format(_ooxml("word", "document.xml"))
    assert fmt.kind == KIND_DOCX
    assert fmt.ext == "docx"
    assert fmt.mime.endswith("wordprocessingml.document")


def test_pptx_by_inner_name() -> None:
    fmt = detect_format(_ooxml("ppt", "presentation.xml"), filename="deck.bin")
    assert fmt.kind == KIND_PPTX
    assert fmt.ext == "pptx"


def test_xlsx_by_inner_name() -> None:
    fmt = detect_format(_ooxml("xl", "workbook.xml"))
    assert fmt.kind == KIND_XLSX
    assert fmt.mime.endswith("spreadsheetml.sheet")


def test_zip_ext_tiebreak() -> None:
    # A bare ZIP signature that is NOT a readable archive → classify by extension.
    fmt = detect_format(b"PK\x03\x04\x00\x00garbage", filename="report.xlsx")
    assert fmt.kind == KIND_XLSX


def test_unclassified_zip_is_unsupported() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("notes/readme.txt", "hello")
    fmt = detect_format(buf.getvalue())  # real ZIP, no OOXML markers, no ext
    assert fmt.kind == KIND_ZIP
    assert not is_supported(fmt)
    with pytest.raises(UnsupportedFormatError):
        ensure_supported(fmt)


def test_html_magic_doctype_and_tag() -> None:
    doctype = detect_format(b"<!DOCTYPE html>\n<html><head></head></html>")
    tag = detect_format(b"\n  <html lang='ru'><body>x</body></html>")
    assert doctype.kind == KIND_HTML and doctype.mime == "text/html"
    assert tag.kind == KIND_HTML


def test_html_by_ext_tiebreak() -> None:
    # Plain-text body but an .html extension → HTML via the extension tiebreak.
    fmt = detect_format(b"just some words, no tags here", filename="page.html")
    assert fmt.kind == KIND_HTML


def test_plain_text() -> None:
    fmt = detect_format("сухой остаток 1000 мг/дм3\n".encode(), filename="spec.txt")
    assert fmt.kind == KIND_TEXT
    assert fmt.mime == "text/plain"
    assert fmt.ext == "txt"
    assert is_supported(fmt)


def test_empty_is_text() -> None:
    assert detect_format(b"").kind == KIND_TEXT
    # A bare UTF-8 BOM with no content is still "empty" → text.
    assert detect_format(b"\xef\xbb\xbf").kind == KIND_TEXT


def test_unknown_ext_falls_back_to_text() -> None:
    # Unrecognized extension but clearly textual content → plain text.
    fmt = detect_format(b"line one\nline two\n", filename="data.weirdext")
    assert fmt.kind == KIND_TEXT


def test_unknown_binary_is_unsupported() -> None:
    # Binary blob (NUL byte, no known magic) → unknown, and not supported.
    fmt = detect_format(b"\x89\x01\x00\x02\xff\xfe\x00\x03", filename="blob.dat")
    assert fmt.kind == KIND_UNKNOWN
    assert fmt.ext == "dat"
    assert not is_supported(fmt)
    with pytest.raises(UnsupportedFormatError):
        ensure_supported(fmt)


def test_is_supported_matrix() -> None:
    supported = detect_format(b"%PDF-1.4")
    unsupported = FormatInfo(mime="application/octet-stream", ext="", kind=KIND_UNKNOWN)
    assert is_supported(supported) is True
    assert is_supported(unsupported) is False
    assert ensure_supported(supported) is supported


def test_format_info_is_frozen_and_as_dict() -> None:
    fmt = detect_format(b"%PDF-1.5")
    assert fmt.as_dict() == {"mime": "application/pdf", "ext": "pdf", "kind": KIND_PDF}
    with pytest.raises(FrozenInstanceError):
        fmt.kind = "text"  # type: ignore[misc]  # frozen dataclass is immutable

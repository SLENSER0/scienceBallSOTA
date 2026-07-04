"""§5.8 Fallback parser adapters: docling → Marker → Unstructured → default.

The §5.8 *protocol* and *priority table* already exist
(:mod:`ingestion_service.parser_protocol` /
:mod:`ingestion_service.parser_priority`). This module supplies the missing
concrete **adapters** and the **per-format fallback orchestrator** that ties
them together, so ingestion can degrade gracefully when the primary parser
(docling) is unavailable — the acceptance criterion of §5.8.

Adapters (each a :class:`~ingestion_service.parser_protocol.DocumentParser`):

- :class:`DoclingParser` — primary. Probes the configured ``DOCLING_SERVE_URL``
  (:data:`kg_common.get_settings().docling_serve_url`); if the service is not
  reachable it raises, which the orchestrator records and *falls through* to the
  next parser. This is exactly the "docling отключён" path from the criterion.
- :class:`MarkerParser` — vendored ``marker`` (``vendor/parsing/marker``).
  Lazily imported; when the optional dependency is absent it raises so the chain
  continues. When present, its markdown output is mapped into a ParsedDoc-like
  dict.
- :class:`UnstructuredParser` — vendored ``unstructured``. Maps its element
  stream (``Title`` / ``NarrativeText`` / ``Table`` / ``ListItem``) into
  ``pages`` + ``tables`` of a ParsedDoc-like dict.
- The pure-python :class:`~ingestion_service.parser_protocol.DefaultDocumentParser`
  is the guaranteed floor of the chain (PDF/DOCX/PPTX/XLSX/TXT/MD), so a document
  always yields a non-empty ``markdown`` even when every optional parser is
  missing.

Every ParsedDoc-like dict produced here also carries a ``markdown`` field and a
``parser_used`` field so downstream chunking/indexing and the §5.8 acceptance
test can assert ``parser_used != "docling"`` with non-empty markdown.

Pure orchestration: no network except the short docling health-probe; heavy ML
libraries are imported lazily and only if actually installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

from ingestion_service.parser_priority import (
    DEFAULT_TABLE,
    PriorityTable,
    resolve_order,
)
from ingestion_service.parser_protocol import (
    DefaultDocumentParser,
    DocumentParser,
    ParsedDocDict,
    ParseResult,
    normalize_fmt,
    parse_with_fallback,
    register_parser,
)

# Formats the structural parsers (docling/marker/unstructured) claim.
_OFFICE_PDF = frozenset({".pdf", ".docx", ".pptx", ".html", ".htm"})
_MARKER_FMTS = frozenset({".pdf"})
_UNSTRUCTURED_FMTS = frozenset({".pdf", ".docx", ".pptx", ".html", ".htm", ".txt"})


# -- markdown helper -----------------------------------------------------------
def to_markdown(doc: ParsedDocDict) -> str:
    """Render a ParsedDoc-like dict to a compact markdown string.

    Пути покрытия: заголовок → страницы (текст) → таблицы (GFM-разметка). Used so
    every adapter emits a non-empty ``markdown`` even when the underlying parser
    only produced plain page text.
    """
    parts: list[str] = []
    title = str(doc.get("title") or "").strip()
    if title:
        parts.append(f"# {title}")
    for page in doc.get("pages") or []:
        text = str((page or {}).get("text") or "").strip()
        if text:
            parts.append(text)
    for tbl in doc.get("tables") or []:
        rows = (tbl or {}).get("rows") or []
        md = _table_to_markdown(rows)
        if md:
            parts.append(md)
    return "\n\n".join(parts).strip()


def _table_to_markdown(rows: list[list[str]]) -> str:
    """GFM table for ``rows`` (first row treated as header); ``""`` when empty."""
    clean = [[str(c) if c is not None else "" for c in r] for r in rows if isinstance(r, list)]
    clean = [r for r in clean if any(cell.strip() for cell in r)]
    if not clean:
        return ""
    width = max(len(r) for r in clean)
    clean = [r + [""] * (width - len(r)) for r in clean]
    header = "| " + " | ".join(clean[0]) + " |"
    sep = "| " + " | ".join(["---"] * width) + " |"
    body = ["| " + " | ".join(r) + " |" for r in clean[1:]]
    return "\n".join([header, sep, *body])


def _finalize(doc: ParsedDocDict, parser_used: str) -> ParsedDocDict:
    """Attach ``parser_used`` + ``markdown`` (if missing) to a ParsedDoc-like dict."""
    out = dict(doc)
    out["parser_used"] = parser_used
    if not str(out.get("markdown") or "").strip():
        out["markdown"] = to_markdown(out)
    return out


# -- docling primary -----------------------------------------------------------
def docling_available(timeout: float = 0.5) -> bool:
    """True when the configured docling-serve endpoint answers a health probe.

    A short HTTP GET against ``DOCLING_SERVE_URL`` (``/health`` first, then root).
    Any error — connection refused, timeout, non-2xx — means *unavailable*, which
    triggers the §5.8 fallback. Never raises.
    """
    import urllib.error
    import urllib.request

    try:
        from kg_common import get_settings

        base = str(get_settings().docling_serve_url or "").rstrip("/")
    except Exception:
        return False
    if not base:
        return False
    for suffix in ("/health", "/"):
        try:
            with urllib.request.urlopen(base + suffix, timeout=timeout) as resp:
                if 200 <= getattr(resp, "status", 200) < 500:
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            continue
    return False


@dataclass(frozen=True)
class DoclingParser:
    """Primary parser adapter — routes to docling-serve (§5, §5.8).

    :meth:`parse` raises when the docling service is unreachable so the
    orchestrator moves on to Marker/Unstructured. When reachable, it defers to the
    existing pure-python :class:`DefaultDocumentParser` output for the local file
    (the HTTP round-trip / rich-layout extraction lives in the ingestion service
    proper); the point here is the *routing decision*, not re-implementing docling.
    """

    name: str = "docling"

    def can_parse(self, fmt: str) -> bool:
        return normalize_fmt(fmt) in _OFFICE_PDF

    def parse(self, path: str | Path) -> ParsedDocDict | None:
        if not docling_available():
            raise RuntimeError("docling-serve unavailable (DOCLING_SERVE_URL not reachable)")
        doc = DefaultDocumentParser().parse(path)
        return None if doc is None else _finalize(doc, "docling")


# -- Marker fallback -----------------------------------------------------------
@dataclass(frozen=True)
class MarkerParser:
    """Vendored ``marker`` PDF→markdown adapter (§5.8, GPL — feature-flagged).

    Marker is an optional dependency (``vendor/parsing/marker``). When it is not
    importable :meth:`parse` raises :class:`ImportError`, which the orchestrator
    records and skips to the next parser. When importable, marker converts the PDF
    to markdown and we wrap that markdown in a ParsedDoc-like dict (single logical
    page); table structure marker surfaces inline in the markdown is preserved.
    """

    name: str = "marker"

    def can_parse(self, fmt: str) -> bool:
        return normalize_fmt(fmt) in _MARKER_FMTS

    def parse(self, path: str | Path) -> ParsedDocDict | None:
        if find_spec("marker") is None:
            raise ImportError("optional dependency 'marker' is not installed")
        # Lazy — only reached when marker is actually present.
        from marker.convert import convert_single_pdf  # type: ignore[import-not-found]
        from marker.models import load_all_models  # type: ignore[import-not-found]

        markdown, _images, meta = convert_single_pdf(str(path), load_all_models())
        text = str(markdown or "").strip()
        if not text:
            return None
        p = Path(path)
        doc: ParsedDocDict = {
            "path": str(p),
            "title": str((meta or {}).get("title") or p.stem),
            "doc_type": "article",
            "file_hash": "",
            "lang": "unknown",
            "pages": [{"page": 1, "text": text}],
            "tables": [],
            "country": None,
            "year": None,
            "full_text": text,
            "markdown": text,
        }
        return _finalize(doc, "marker")


# -- Unstructured fallback -----------------------------------------------------
@dataclass(frozen=True)
class UnstructuredParser:
    """Vendored ``unstructured`` element-stream adapter (§5.8, Apache-2.0).

    Maps the ``unstructured`` element taxonomy into a ParsedDoc-like dict:
    ``Title``/``NarrativeText``/``ListItem`` become page text (grouped by
    ``page_number``); ``Table`` elements become ``tables`` entries with a parsed
    HTML grid when ``text_as_html`` metadata is present, else a single-row grid.
    Absent dependency → :class:`ImportError` (chain continues).
    """

    name: str = "unstructured"

    def can_parse(self, fmt: str) -> bool:
        return normalize_fmt(fmt) in _UNSTRUCTURED_FMTS

    def parse(self, path: str | Path) -> ParsedDocDict | None:
        if find_spec("unstructured") is None:
            raise ImportError("optional dependency 'unstructured' is not installed")
        from unstructured.partition.auto import partition  # type: ignore[import-not-found]

        elements = partition(filename=str(path))
        page_text: dict[int, list[str]] = {}
        tables: list[dict] = []
        for el in elements:
            category = type(el).__name__
            meta = getattr(el, "metadata", None)
            page_no = int(getattr(meta, "page_number", None) or 1)
            body = str(getattr(el, "text", "") or "").strip()
            if category == "Table":
                html = getattr(meta, "text_as_html", None)
                rows = _html_table_rows(html) if html else ([[body]] if body else [])
                if rows:
                    tables.append({"page": page_no, "rows": rows})
                continue
            if body:  # Title / NarrativeText / ListItem / etc → page text
                page_text.setdefault(page_no, []).append(body)
        pages = [
            {"page": pn, "text": "\n".join(lines)}
            for pn, lines in sorted(page_text.items())
        ]
        if not pages and not tables:
            return None
        full_text = "\n\n".join(p["text"] for p in pages)
        p = Path(path)
        doc: ParsedDocDict = {
            "path": str(p),
            "title": p.stem,
            "doc_type": "article",
            "file_hash": "",
            "lang": "unknown",
            "pages": pages,
            "tables": tables,
            "country": None,
            "year": None,
            "full_text": full_text,
        }
        return _finalize(doc, "unstructured")


def _html_table_rows(html: str | None) -> list[list[str]]:
    """Parse an ``unstructured`` ``text_as_html`` table into rows of cell text."""
    if not html:
        return []
    import re
    from html import unescape

    rows: list[list[str]] = []
    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, re.I | re.S):
        cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, re.I | re.S)
        rows.append([unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in cells])
    return [r for r in rows if any(c for c in r)]


# -- chain assembly + orchestration --------------------------------------------
def build_chain_for_format(
    fmt: str, *, table: PriorityTable = DEFAULT_TABLE
) -> list[DocumentParser]:
    """Ordered parser instances for ``fmt`` per the priority ``table`` (§5.8).

    Reads the configured order (e.g. ``pdf → docling, unstructured, default``;
    ``html → unstructured, docling, default``) and materialises one adapter per
    name. Unknown names in the table are skipped; ``default`` is always appended
    as a last-resort floor if the table did not already include it.
    """
    registry = available_parsers()
    order = list(resolve_order(table, fmt))
    chain: list[DocumentParser] = [registry[name] for name in order if name in registry]
    if not any(p.name == "default" for p in chain):
        chain.append(DefaultDocumentParser())
    return chain


def available_parsers() -> dict[str, DocumentParser]:
    """Name → adapter for every §5.8 parser (docling/marker/unstructured/default)."""
    return {
        "docling": DoclingParser(),
        "marker": MarkerParser(),
        "unstructured": UnstructuredParser(),
        "default": DefaultDocumentParser(),
    }


def parser_readiness() -> dict[str, dict[str, object]]:
    """Per-parser availability snapshot for a status endpoint / diagnostics.

    ``docling`` reports whether ``DOCLING_SERVE_URL`` answers; ``marker`` /
    ``unstructured`` report whether their optional dependency is importable;
    ``default`` is always ready. ``available`` drives the UI's health badges.
    """
    return {
        "docling": {
            "available": docling_available(),
            "kind": "service",
            "formats": sorted(_OFFICE_PDF),
        },
        "marker": {
            "available": find_spec("marker") is not None,
            "kind": "optional-dep",
            "formats": sorted(_MARKER_FMTS),
        },
        "unstructured": {
            "available": find_spec("unstructured") is not None,
            "kind": "optional-dep",
            "formats": sorted(_UNSTRUCTURED_FMTS),
        },
        "default": {
            "available": True,
            "kind": "builtin",
            "formats": ["pdf", "docx", "pptx", "xlsx", "txt", "md"],
        },
    }


def parse_document_with_fallback(
    path: str | Path, *, fmt: str | None = None, table: PriorityTable = DEFAULT_TABLE
) -> ParseResult:
    """Parse ``path`` through the §5.8 fallback chain; return a :class:`ParseResult`.

    The winning parser's name is in :attr:`ParseResult.parser` and mirrored in the
    ParsedDoc-like dict's ``parser_used``. Because the pure-python default parser
    anchors the chain, a well-formed document always parses; when docling is down
    the winner is Marker/Unstructured/default — never ``docling`` — with non-empty
    ``markdown`` (the §5.8 acceptance criterion).
    """
    resolved_fmt = fmt if fmt is not None else Path(path).suffix
    chain = build_chain_for_format(resolved_fmt, table=table)
    return parse_with_fallback(path, chain, fmt=resolved_fmt)


def register_fallback_parsers() -> list[str]:
    """Register docling/marker/unstructured in the shared protocol registry.

    ``default`` is already registered by :mod:`ingestion_service.parser_protocol`
    at import time; this adds the three structural adapters so
    :func:`~ingestion_service.parser_protocol.get_parser` can resolve them by name.
    Idempotent — returns the registered keys.
    """
    keys = [register_parser(p) for name, p in available_parsers().items() if name != "default"]
    return keys

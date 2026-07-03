"""§5.8 ``DocumentParser`` protocol + fallback orchestration.

A small, dependency-free layer that lets ingestion try several parsers for a
document and gracefully degrade when one fails (например, a corrupt PDF falls
back to a plain-text reader). It defines:

- :class:`DocumentParser` — a structural :class:`typing.Protocol` with
  ``can_parse(fmt) -> bool`` and ``parse(path) -> ParsedDoc-like dict | None``;
- a process-wide **registry** (:func:`register_parser` / :func:`get_parser`);
- :func:`parse_with_fallback` — try parsers *in order*, skip the ones that do
  not claim the format, catch per-parser failures, and return the first success
  wrapped in a :class:`ParseResult` (which parser won + collected errors);
- :class:`DefaultDocumentParser` — wraps
  :func:`ingestion_service.parsers.parse_document` (PDF/DOCX/PPTX/XLSX/TXT/MD)
  and normalizes its :class:`~ingestion_service.parsers.ParsedDoc` into a dict.

Pure Python: no LLM / network / optional ML stack. Works on RU + EN paths.
``parsers.py`` is intentionally *not* modified — it is only wrapped here.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ingestion_service.parsers import SUPPORTED, ParsedDoc, parse_document

# ParsedDoc-like dict (нормализованный документ) returned by ``parse``.
ParsedDocDict = dict[str, Any]


@runtime_checkable
class DocumentParser(Protocol):
    """Structural contract for a document parser (§5.8).

    Реализация declares which formats it handles via :meth:`can_parse` and
    turns a path into a normalized ``ParsedDoc``-like dict via :meth:`parse`
    (or ``None`` when it cannot produce a usable document). A human-readable
    :attr:`name` identifies the parser in :class:`ParseResult`.
    """

    #: Stable identifier used in the registry and in ``ParseResult.parser``.
    name: str

    def can_parse(self, fmt: str) -> bool:
        """True when this parser claims ``fmt`` (расширение like ``.pdf``/``pdf``)."""
        ...

    def parse(self, path: str | Path) -> ParsedDocDict | None:
        """Parse ``path`` → ParsedDoc-like dict, or ``None`` on soft failure."""
        ...


@dataclass(frozen=True)
class ParseError:
    """One parser's failure while orchestrating a fallback (§5.8)."""

    parser: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"parser": self.parser, "message": self.message}


@dataclass(frozen=True)
class ParseResult:
    """Outcome of :func:`parse_with_fallback` (§5.8).

    - ``ok``     — a parser produced a document (документ получен);
    - ``parser`` — :attr:`DocumentParser.name` of the winner, else ``None``;
    - ``doc``    — the ParsedDoc-like dict, else ``None``;
    - ``errors`` — collected :class:`ParseError`\\ s from parsers that were
      *tried* and failed (skipped-by-``can_parse`` parsers are not errors).
    """

    ok: bool
    parser: str | None = None
    doc: ParsedDocDict | None = None
    errors: tuple[ParseError, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "parser": self.parser,
            "doc": self.doc,
            "errors": [e.as_dict() for e in self.errors],
        }


# --- format helpers ------------------------------------------------------------
def normalize_fmt(fmt: str) -> str:
    """Normalize a format hint to a lowercase, dot-prefixed extension.

    Accepts ``"pdf"``, ``".PDF"`` or a whole filename (``"report.pdf"``) and
    returns ``".pdf"``. Empty / whitespace-only input yields ``""``.
    """
    f = fmt.strip().lower()
    if not f:
        return ""
    if f.startswith("."):
        return f
    if "." in f:  # looks like a filename → take its suffix
        return Path(f).suffix
    return f".{f}"


# --- default parser (wraps parsers.parse_document) -----------------------------
@dataclass(frozen=True)
class DefaultDocumentParser:
    """Default parser wrapping :func:`ingestion_service.parsers.parse_document`.

    Claims the extensions in :data:`ingestion_service.parsers.SUPPORTED`
    (PDF/DOCX/PPTX/XLSX/XLS/TXT/MD) and normalizes the returned
    :class:`~ingestion_service.parsers.ParsedDoc` into a dict via
    :func:`parsed_doc_to_dict`. Never edits ``parsers.py`` — only calls it.
    """

    name: str = "default"

    def can_parse(self, fmt: str) -> bool:
        return normalize_fmt(fmt) in SUPPORTED

    def parse(self, path: str | Path) -> ParsedDocDict | None:
        doc = parse_document(path)
        return None if doc is None else parsed_doc_to_dict(doc)


def parsed_doc_to_dict(doc: ParsedDoc) -> ParsedDocDict:
    """Normalize a :class:`ParsedDoc` into a JSON-friendly ParsedDoc-like dict."""
    return {
        "path": doc.path,
        "title": doc.title,
        "doc_type": doc.doc_type,
        "file_hash": doc.file_hash,
        "lang": doc.lang,
        "pages": [{"page": page_no, "text": text} for page_no, text in doc.pages],
        "tables": [{"page": tbl.page, "rows": tbl.rows} for tbl in doc.tables],
        "country": doc.country,
        "year": doc.year,
        "full_text": doc.full_text,
    }


# --- registry ------------------------------------------------------------------
_REGISTRY: dict[str, DocumentParser] = {}


def register_parser(parser: DocumentParser, *, name: str | None = None) -> str:
    """Register ``parser`` under ``name`` (default: its :attr:`~DocumentParser.name`).

    Returns the key used. Re-registering the same key overwrites (последняя
    регистрация выигрывает), which keeps the call idempotent for a fixed parser.
    """
    key = name or getattr(parser, "name", None) or type(parser).__name__
    _REGISTRY[key] = parser
    return key


def get_parser(name: str) -> DocumentParser | None:
    """Return the registered parser for ``name``, or ``None`` if absent."""
    return _REGISTRY.get(name)


def registered_parsers() -> dict[str, DocumentParser]:
    """A shallow copy of the registry (snapshot; mutating it is safe)."""
    return dict(_REGISTRY)


def unregister_parser(name: str) -> bool:
    """Drop ``name`` from the registry; return ``True`` if it was present."""
    return _REGISTRY.pop(name, None) is not None


# --- fallback orchestration ----------------------------------------------------
def parse_with_fallback(
    path: str | Path,
    parsers: Iterable[DocumentParser],
    *,
    fmt: str | None = None,
) -> ParseResult:
    """Try ``parsers`` in order; return the first success as a :class:`ParseResult`.

    For each parser: skip it silently when :meth:`~DocumentParser.can_parse` is
    ``False`` (неизвестный формат — не ошибка); otherwise call
    :meth:`~DocumentParser.parse`. A raised exception *or* a ``None`` return is
    recorded as a :class:`ParseError` and the next parser is tried. The first
    parser to return a document wins (its errors-so-far are preserved on the
    result). If every parser is skipped or fails, ``ok`` is ``False`` and
    ``errors`` holds one entry per parser that was actually tried.

    ``fmt`` overrides the format hint; by default it is derived from the path
    suffix, so ``can_parse`` sees ``".pdf"`` for ``report.pdf``.
    """
    resolved_fmt = fmt if fmt is not None else Path(path).suffix
    errors: list[ParseError] = []
    for parser in parsers:
        name = getattr(parser, "name", None) or type(parser).__name__
        try:
            if not parser.can_parse(resolved_fmt):
                continue  # неизвестный формат: пропускаем без ошибки
            doc = parser.parse(path)
        except Exception as exc:  # defensive: a parser must never break the chain
            errors.append(ParseError(name, str(exc)[:200]))
            continue
        if doc is None:
            errors.append(ParseError(name, "parser returned no document"))
            continue
        return ParseResult(ok=True, parser=name, doc=doc, errors=tuple(errors))
    return ParseResult(ok=False, parser=None, doc=None, errors=tuple(errors))


def default_parsers() -> list[DocumentParser]:
    """The built-in parser chain (currently just :class:`DefaultDocumentParser`)."""
    return [DefaultDocumentParser()]


# Register the default parser at import so ``get_parser("default")`` works.
register_parser(DefaultDocumentParser())
